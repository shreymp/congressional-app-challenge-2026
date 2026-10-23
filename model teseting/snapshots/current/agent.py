"""scam-guard: LiveKit agent that discloses recording, then scores the caller's voice.

How it gets the audio
  Grandma's cell forwards all calls to the LiveKit number. LiveKit puts each call in its own
  room whose name starts with "call-" (dispatch rule "cac-inbound") and dispatches the agent
  named "scam-guard" into it. After pickup it briefly publishes the recording notice, then
  only processes the phone caller's track.

What it does per call
  0. Rings grandma's app (senior_ring.py): as soon as the phone caller is in the room it sends
     the open app an "incoming call" invite through the app's lobby room. The app joins this
     room and publishes its microphone when she answers; that is what answers the phone call.
     Also handles no answer (a stub for now) and hangs up the caller after she hangs up.
  1. Finds the SIP participant (the phone caller) and logs its attributes, including the
     caller number LiveKit saw. That answers "does forwarding keep the real caller ID?".
  2. Streams the caller's audio at 16 kHz, retaining contiguous four-second windows.
  3. Checks about once per second for a distinct eligible window and scores it in a worker
     thread (never blocking the audio loop), accumulates evidence, and publishes to the room on
  2. Plays "This call is being recorded." to the answered room before starting any caller
     stream, transcription or recording. If playback fails, all of those stay disabled.
     Then streams the caller's audio at 16 kHz, keeping the last ~4 s of speech.
  3. About once per second, scores that window with the deepfake detector in a worker thread
     (never blocking the audio loop), smooths it, and publishes a JSON update to the room on
     topic "scam-guard.risk". Grandma's app (and tools/watch_risk.py) listen on that topic.
  4. Optionally saves the caller's audio for building phone-domain training data
     (RECORD_CALLER_AUDIO=1). Only for calls where everyone has agreed to be recorded.

Run locally:  python agent.py dev      (see README.md)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime

import numpy as np
from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import AgentServer, AutoSubscribe, JobContext, JobProcess, cli

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, ".env.local"))

import detector_adapter
import transcript_pipeline
from risk import combine
from scoring import AudioScoringSession
from risk_protocol import RISK_TOPIC, RiskPublisher
import senior_ring
from recording_notice import NOTICE_TIMEOUT_SEC, play_recording_notice

AGENT_NAME = "scam-guard"          # must match the dispatch rule in LiveKit Cloud
SAMPLE_RATE = 16000
SCORE_EVERY_SEC = float(os.environ.get("SCORE_EVERY_SEC", "1.0"))
RECORD = os.environ.get("RECORD_CALLER_AUDIO", "0") == "1"
RECORD_DIR = os.path.join(HERE, "recordings")

log = logging.getLogger("scam-guard")


def prewarm(proc: JobProcess) -> None:
    """Runs once per worker process, before any call, so the 650 MB model is already loaded."""
    try:
        proc.userdata["detector"] = detector_adapter.load()
        log.info("detector loaded on %s", proc.userdata["detector"].device)
    except Exception as e:
        proc.userdata["detector_error"] = f"{type(e).__name__}: {e}"[:300]
        # Ringing and media remain usable even when the model cannot initialize.
        proc.userdata["detector"] = None
        log.exception("detector unavailable; calls will continue without voice labels")

    proc.userdata["stt_model"] = None
    proc.userdata["transcript_state"] = "disabled"
    try:
        proc.userdata["stt_model"] = transcript_pipeline.load_model()
        if proc.userdata["stt_model"] is not None:
            proc.userdata["transcript_state"] = "listening"
    except Exception as e:
        proc.userdata["stt_error"] = f"{type(e).__name__}: {e}"[:300]
        proc.userdata["transcript_state"] = "stt_unavailable"
        log.exception("Vosk unavailable; calls continue without transcript scores")


server = AgentServer(
    setup_fnc=prewarm,
    num_idle_processes=1,            # keep one process warm with the model loaded
    initialize_process_timeout=180,  # model load + MPS warm-up takes longer than the 10 s default
    job_memory_warn_mb=4000,         # the model alone is ~1-2 GB in RAM; default warns at 1000
)


@server.rtc_session(agent_name=AGENT_NAME)
async def scam_guard(ctx: JobContext) -> None:
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    # 0. Ring grandma's app for the phone caller. Starts its own task and returns at once; it
    #    must not wait for step 1, because nothing answers the call until she has been rung.
    probe = ctx.room.name.startswith("backend-probe-") and ctx.job.metadata == "cac-backend-probe-v1"
    if not probe:
        senior_ring.start_for_job(ctx)
    # Steps 1-4 (scoring) must never take the ring down with them. An exception that escapes this
    # function makes the framework disconnect the agent and run the shutdown callbacks, which
    # cancels the ring: an unanswered call would stop ringing, and when grandma hangs up the room
    # would not be deleted, leaving the phone caller connected to nobody. Returning normally keeps
    # the job alive until the room disconnects, so the ring keeps supervising the call.
    try:
        await _score_call(ctx, probe=probe)
    except Exception as e:
        if isinstance(e, RuntimeError) and not ctx.room.isconnected():
            # wait_for_participant raises this when the room closes first, e.g. the caller gave up
            # while it was still ringing. Normal, not an error.
            log.info("room closed before scoring finished: %s", e)
        else:
            log.exception("scoring stopped; the senior ring keeps running")


async def _score_call(ctx: JobContext, probe: bool = False) -> None:
    room = ctx.room
    det = ctx.proc.userdata.get("detector")
    session = AudioScoringSession(det, detector_adapter.thresholds(det)) if det is not None else None
    caller = (await ctx.wait_for_participant(identity="backend-probe-caller") if probe else
              await ctx.wait_for_participant(kind=rtc.ParticipantKind.PARTICIPANT_KIND_SIP))
    if not probe:
        # wait_for_participant returns an ACTIVE SIP caller: the senior's microphone has
        # answered the call. Do not publish the notice while the app is still ringing.
        try:
            await asyncio.wait_for(play_recording_notice(room), timeout=NOTICE_TIMEOUT_SEC)
        except Exception:
            log.exception("recording notice failed; analysis and recording disabled for this call")
            publisher = RiskPublisher(room.name, caller.identity, getattr(det, "mode", "real"))
            try:
                await room.local_participant.publish_data(json.dumps(publisher.message({
                    "type": "status", "state": "unavailable", "reason": "recording_notice_failed",
                    "transcript": {"state": "disabled", "probability": None},
                })), reliable=True, topic=RISK_TOPIC)
            except Exception:
                log.warning("notice failure status could not be sent", exc_info=True)
            return
    caller_number = caller.attributes.get("sip.phoneNumber", "unknown")
    publisher = RiskPublisher(room.name, caller.identity, getattr(det, "mode", "real"))
    t_start = time.monotonic()

    transcript = None
    transcript_state = ctx.proc.userdata.get("transcript_state", "disabled")
    if ctx.proc.userdata.get("stt_model") is not None:
        try:
            transcript = await asyncio.to_thread(transcript_pipeline.for_call, ctx.proc.userdata["stt_model"])
            transcript.start()
        except Exception:
            transcript_state = "stt_unavailable"
            log.exception("caller transcription could not start")

    frames = [0]

    async def publish(payload: dict) -> None:
        if probe:
            # CI probe rooms only: report why scoring is or is not running.
            payload = {**payload, "diag": await asyncio.to_thread(_probe_diag, ctx.proc.userdata, frames[0])}
        text_state = transcript.snapshot() if transcript else {"state": transcript_state, "probability": None}
        payload = {**payload, "transcript": text_state}
        if payload.get("type") == "risk":
            payload["level"] = combine(payload["deepfake"]["level"], text_state["probability"])
        msg = publisher.message({**payload, "t": round(time.monotonic() - t_start, 2)})
        try:
            await room.local_participant.publish_data(
                json.dumps(msg, allow_nan=False), reliable=True, topic=RISK_TOPIC)
        except Exception:
            log.warning("risk update could not be sent", exc_info=True)

    async def heartbeat() -> None:
        # Also reaches a phone that joins after the agent's initial status was sent.
        while room.isconnected():
            payload = session.payload(time.monotonic()) if session else {"type": "status", "state": "unavailable"}
            await publish(payload)
            await asyncio.sleep(2)

    heartbeat_task = asyncio.create_task(heartbeat())
    score_task = None
    stream = None
    recorded: list[np.ndarray] = []

    async def score_once(audio, generation) -> None:
        try:
            result = await asyncio.to_thread(det.score_window, audio)
            session.refresh(time.monotonic())
            session.complete(result, generation)
            await publish(session.payload(time.monotonic()))
        except asyncio.CancelledError:
            raise
        except Exception:
            session.failed()
            await publish(session.payload(time.monotonic()))
            log.exception("voice scoring failed; call continues")

    async def stop_scoring() -> None:
        heartbeat_task.cancel()
        if score_task is not None:
            score_task.cancel()
        await asyncio.gather(heartbeat_task, *([score_task] if score_task is not None else []),
                             return_exceptions=True)
        if transcript is not None:
            await transcript.aclose()

    ctx.add_shutdown_callback(stop_scoring)

    try:
        if session is None and transcript is None:
            # Keep notifying late joiners while allowing the ring supervisor to run.
            await heartbeat_task
            return
        stream = rtc.AudioStream.from_participant(
            participant=caller, track_source=rtc.TrackSource.SOURCE_MICROPHONE,
            sample_rate=SAMPLE_RATE, num_channels=1)
        next_score = time.monotonic() + SCORE_EVERY_SEC
        async for event in stream:
            now = time.monotonic()
            frames[0] += 1
            if transcript is not None:
                transcript.push(event.frame.data)
            if session is not None:
                session.push(event.frame.data, now)
            if RECORD:
                recorded.append(np.frombuffer(event.frame.data, dtype=np.int16).copy())
            if session is not None and now >= next_score and (score_task is None or score_task.done()):
                next_score = now + SCORE_EVERY_SEC
                snapshot = session.snapshot(now)
                if snapshot is not None:
                    # Capture a copy on the audio loop. Never read its rolling buffer in a worker.
                    score_task = asyncio.create_task(score_once(*snapshot))
    finally:
        await stop_scoring()
        if stream is not None:
            await stream.aclose()
        if RECORD and recorded:
            await asyncio.to_thread(_save_wav, np.concatenate(recorded), caller_number)


def _save_wav(pcm: np.ndarray, caller_number: str) -> None:
    import soundfile as sf
    os.makedirs(RECORD_DIR, exist_ok=True)
    safe = "".join(c for c in caller_number if c.isalnum()) or "unknown"
    path = os.path.join(RECORD_DIR, f"{datetime.now():%Y%m%d-%H%M%S}_{safe}.wav")
    sf.write(path, pcm, SAMPLE_RATE, subtype="PCM_16")
    log.info("saved caller audio to %s", path)


def _probe_diag(userdata: dict, frames: int) -> dict:
    """Transcript-free health facts for the CI backend probe (probe rooms only)."""
    import urllib.request
    out = {"detector_error": userdata.get("detector_error"), "stt_error": userdata.get("stt_error"),
           "frames": frames, "cpus": os.cpu_count(), "pid": os.getpid()}
    for port in (8000, 3000):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as response:
                out[f"svc{port}"] = response.status
        except Exception as e:
            out[f"svc{port}"] = f"{type(e).__name__}: {e}"[:160]
    for name in ("memory.max", "memory.current", "memory.peak", "memory.events", "cpu.max"):
        try:
            with open("/sys/fs/cgroup/" + name) as f:
                out[name] = " ".join(f.read().split())[:200]
        except OSError:
            pass
    out["proxy_env"] = sorted(k for k in os.environ if k.lower() in ("http_proxy", "https_proxy", "no_proxy", "all_proxy"))
    return out


if __name__ == "__main__":
    cli.run_app(server)
