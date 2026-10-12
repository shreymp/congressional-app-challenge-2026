"""scam-guard: silent LiveKit agent that scores the phone caller's voice in real time.

How it gets the audio
  Grandma's cell forwards all calls to the LiveKit number. LiveKit puts each call in a room
  named call-<caller-number> (dispatch rule "cac-inbound") and dispatches the agent named
  "scam-guard" into it. The agent never publishes audio; it only subscribes to the phone
  caller's track, so nobody on the call can hear it.

What it does per call
  1. Finds the SIP participant (the phone caller) and logs its attributes, including the
     caller number LiveKit saw. That answers "does forwarding keep the real caller ID?".
  2. Streams the caller's audio at 16 kHz, keeps the last ~4 s of speech.
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

import detector_adapter
from audio_window import VoicedWindow
from risk import RiskEngine, combine

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, ".env.local"))

AGENT_NAME = "scam-guard"          # must match the dispatch rule in LiveKit Cloud
RISK_TOPIC = "scam-guard.risk"
SAMPLE_RATE = 16000
SCORE_EVERY_SEC = float(os.environ.get("SCORE_EVERY_SEC", "1.0"))
RECORD = os.environ.get("RECORD_CALLER_AUDIO", "0") == "1"
RECORD_DIR = os.path.join(HERE, "recordings")

log = logging.getLogger("scam-guard")


def prewarm(proc: JobProcess) -> None:
    """Runs once per worker process, before any call, so the 650 MB model is already loaded."""
    proc.userdata["detector"] = detector_adapter.load()
    log.info("detector loaded on %s", proc.userdata["detector"].device)


server = AgentServer(
    setup_fnc=prewarm,
    num_idle_processes=1,            # keep one process warm with the model loaded
    initialize_process_timeout=180,  # model load + MPS warm-up takes longer than the 10 s default
    job_memory_warn_mb=4000,         # the model alone is ~1-2 GB in RAM; default warns at 1000
)


@server.rtc_session(agent_name=AGENT_NAME)
async def scam_guard(ctx: JobContext) -> None:
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    room = ctx.room
    det = ctx.proc.userdata.get("detector") or detector_adapter.load()
    elevated_thr, high_thr = detector_adapter.thresholds(det)
    risk = RiskEngine(elevated_threshold=elevated_thr, high_threshold=high_thr)
    window = VoicedWindow(sample_rate=SAMPLE_RATE, window_sec=det.meta["window_sec"])

    # 1. Find the phone caller. Only SIP participants count; grandma's app is a STANDARD one.
    caller = await ctx.wait_for_participant(kind=rtc.ParticipantKind.PARTICIPANT_KIND_SIP)
    attrs = dict(caller.attributes)
    log.info("room=%s caller identity=%s", room.name, caller.identity)
    log.info("SIP attributes: %s", json.dumps(attrs, indent=2))
    caller_number = attrs.get("sip.phoneNumber", "unknown")

    async def publish(msg: dict) -> None:
        msg.update({"room": room.name, "t": round(time.monotonic() - t_start, 2)})
        try:
            await room.local_participant.publish_data(json.dumps(msg), reliable=True, topic=RISK_TOPIC)
        except Exception as e:                      # never let a send failure kill the call
            log.warning("publish failed: %s", e)

    t_start = time.monotonic()
    await publish({"type": "status", "state": "monitoring", "caller": caller_number,
                   "detector_device": det.device})

    # 2. Stream the caller's microphone track, resampled by LiveKit to 16 kHz mono int16.
    stream = rtc.AudioStream.from_participant(
        participant=caller, track_source=rtc.TrackSource.SOURCE_MICROPHONE,
        sample_rate=SAMPLE_RATE, num_channels=1,
    )

    recorded: list[np.ndarray] = []
    busy = False
    stats = {"scored": 0, "skipped_busy": 0}

    async def score_once() -> None:
        nonlocal busy
        busy = True
        try:
            audio = window.snapshot()
            r = await asyncio.to_thread(det.score_window, audio)   # 3. off the event loop
            state = risk.update(r["p_fake"], r.get("logit"))
            stats["scored"] += 1
            level = combine(state["level"], transcript_probability=None)  # TODO: transcript branch
            await publish({"type": "risk", "level": level, "deepfake": state,
                           "transcript": None, "infer_ms": round(r["infer_ms"], 1),
                           "voiced_sec": round(window.total_voiced / SAMPLE_RATE, 1)})
            log.info("logit=%.2f smoothed_logit=%.2f level=%s infer=%.0fms",
                     state["logit_last"], state["logit_smoothed"], level, r["infer_ms"])
        except Exception:
            log.exception("scoring failed")
        finally:
            busy = False

    next_score = time.monotonic() + SCORE_EVERY_SEC
    try:
        async for event in stream:
            frame = event.frame
            window.push_int16(frame.data)
            if RECORD:
                recorded.append(np.frombuffer(frame.data, dtype=np.int16).copy())
            now = time.monotonic()
            if now >= next_score and window.ready():
                next_score = now + SCORE_EVERY_SEC
                if busy:
                    stats["skipped_busy"] += 1    # model slower than SCORE_EVERY_SEC; don't queue up
                else:
                    asyncio.create_task(score_once())
    finally:
        await stream.aclose()
        log.info("call ended: %s, voiced %.1fs of %.1fs", stats,
                 window.total_voiced / SAMPLE_RATE, window.total_seen / SAMPLE_RATE)
        if RECORD and recorded:
            _save_wav(np.concatenate(recorded), caller_number)


def _save_wav(pcm: np.ndarray, caller_number: str) -> None:
    import soundfile as sf
    os.makedirs(RECORD_DIR, exist_ok=True)
    safe = "".join(c for c in caller_number if c.isalnum()) or "unknown"
    path = os.path.join(RECORD_DIR, f"{datetime.now():%Y%m%d-%H%M%S}_{safe}.wav")
    sf.write(path, pcm, SAMPLE_RATE, subtype="PCM_16")
    log.info("saved caller audio to %s", path)


if __name__ == "__main__":
    cli.run_app(server)
