"""Send fixture speech through the cloud models; optionally ring the simulator too."""
import argparse
import asyncio
from datetime import timedelta
import json
import math
import os
from pathlib import Path
import uuid
import sys
import time

from probe_checks import ProbeEvidence

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly
from livekit import api, rtc


def describe(message):
    """One-line, transcript-free summary of an agent update for CI diagnostics."""
    text = message.get("transcript") or {}
    voice = message.get("deepfake") or {}
    return json.dumps({
        "type": message.get("type"), "state": message.get("state"), "model": message.get("model"),
        "schema": message.get("schema"), "seq": message.get("sequence"), "t": message.get("t"),
        "infer_ms": message.get("infer_ms"), "voiced_sec": message.get("voiced_sec"),
        "deepfake_p_last": voice.get("p_last"), "deepfake_level": voice.get("level"),
        "text_state": text.get("state"), "text_p": text.get("probability"),
        "text_rev": text.get("revision"), "text_scored_rev": text.get("scored_revision"),
        "text_chars": text.get("chars"), "diag": message.get("diag")})


async def attempt(wav, timeout, min_seconds=35, ring_app=False):
    audio, sr = sf.read(wav, dtype="float32", always_2d=True)
    audio = audio.mean(axis=1)
    if not len(audio) or not np.isfinite(audio).all():
        raise ValueError("Use a nonempty speech WAV")
    audio = resample_poly(audio, 16000 // math.gcd(sr, 16000), sr // math.gcd(sr, 16000))
    pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
    name = "backend-probe-" + uuid.uuid4().hex
    identity = "backend-probe-caller"
    token = (api.AccessToken().with_identity(identity).with_ttl(timedelta(minutes=10))
             .with_grants(api.VideoGrants(room_join=True, room=name)).to_jwt())
    room = rtc.Room()
    passed = asyncio.Event()
    expected = None
    if os.environ.get("EXPECTED_JEV_VERSION"):
        expected = (os.environ["EXPECTED_JEV_VERSION"], os.environ["EXPECTED_JEV_SHA256"])
    evidence = ProbeEvidence(name, identity, min_seconds, expected_jev=expected)
    ring = None
    microphone = {"heard": False}
    tasks = []
    seen = {"count": 0, "last": None}

    @room.on("participant_connected")
    def joined(participant):
        print("probe: participant joined", participant.identity, "kind", participant.kind, flush=True)

    @room.on("data_received")
    def receive(packet):
        if packet.topic != "scam-guard.risk":
            return
        try:
            message = json.loads(packet.data)
            if not isinstance(message, dict):
                return
            seen["count"] += 1
            line = describe(message)
            # Print only when the update changes shape, so a 90 s attempt stays readable.
            key = json.loads(line)
            for volatile in ("seq", "t", "infer_ms", "voiced_sec", "deepfake_p_last", "text_p",
                             "text_rev", "text_scored_rev", "text_chars", "diag"):
                key.pop(volatile)
            if key != seen["last"]:
                seen["last"] = key
                print("probe: update", line, flush=True)
            elif seen["count"] % 10 == 0:
                print("probe: update", line, flush=True)
            is_agent = packet.participant is not None and packet.participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_AGENT
            if evidence.observe(message, is_agent=is_agent, now=time.monotonic()):
                if not ring_app or (ring is not None and ring.answered and microphone["heard"]):
                    passed.set()
        except (ValueError, TypeError, AttributeError):
            return

    async def listen(track):
        stream = rtc.AudioStream(track, sample_rate=16000, num_channels=1)
        try:
            async for event in stream:
                pcm = np.frombuffer(event.frame.data, dtype=np.int16).astype(np.float32) / 32768
                if len(pcm) and float(np.sqrt(np.mean(pcm * pcm))) > 0.0032:
                    if not microphone["heard"]:
                        print("probe: simulator microphone speech received", flush=True)
                    microphone["heard"] = True
        finally:
            await stream.aclose()

    if ring_app:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend/AI Deepfake Pipeline/LiveKit Setup"))
        import senior_ring

        @room.on("track_subscribed")
        def subscribed(track, publication, participant):
            if participant.identity == senior_ring.SENIOR_IDENTITY and track.kind == rtc.TrackKind.KIND_AUDIO:
                tasks.append(asyncio.create_task(listen(track)))

    async def play(source):
        while not passed.is_set():
            for offset in range(0, len(pcm), 320):
                frame = pcm[offset:offset + 320]
                if len(frame):
                    await source.capture_frame(rtc.AudioFrame(frame.tobytes(), 16000, 1, len(frame)))

    async with api.LiveKitAPI() as lk:
        playback = None
        try:
            await room.connect(os.environ["LIVEKIT_URL"], token)
            await lk.agent_dispatch.create_dispatch(api.CreateAgentDispatchRequest(
                room=name, agent_name="scam-guard", metadata="cac-backend-probe-v1"))
            source = rtc.AudioSource(16000, 1)
            track = rtc.LocalAudioTrack.create_audio_track("consented-fixture", source)
            await room.local_participant.publish_track(track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE))
            playback = asyncio.create_task(play(source))
            if ring_app:
                ring = senior_ring.SeniorRing(
                    lk=lk, room=room, caller_identity=identity, caller_is_local=True,
                    handle="+15555550100", caller_name="Cloud pipeline test",
                    delete_room=lambda: lk.room.delete_room(api.DeleteRoomRequest(room=name)))
                tasks.append(asyncio.create_task(ring.run()))
                print("probe: Accept in the simulator, listen for fixture speech, then speak into the Mac microphone.", flush=True)
            try:
                await asyncio.wait_for(passed.wait(), timeout)
            except asyncio.TimeoutError:
                print(f"probe: {seen['count']} agent updates received in room {name}; "
                      f"remote participants: {[p.identity for p in room.remote_participants.values()]}", flush=True)
                raise
            summary = dict(evidence.summary)
            if ring_app:
                summary.update(simulator_answered=ring.answered, simulator_microphone=microphone["heard"])
            print("FULL CALL PROBE PASSED" if ring_app else "BACKEND PROBE PASSED", json.dumps(summary))
        finally:
            for task in tasks + ([playback] if playback else []):
                task.cancel()
            await asyncio.gather(*tasks, *([playback] if playback else []), return_exceptions=True)
            await room.disconnect()
            try:
                await lk.room.delete_room(api.DeleteRoomRequest(room=name))
            except api.TwirpError as error:
                if error.code != api.TwirpErrorCode.NOT_FOUND:
                    raise


async def probe(wav, timeout, attempts=1, min_seconds=35, ring_app=False):
    """Retry with a fresh room: right after `lk agent deploy` the previous version can still be
    serving jobs for a short while, and it ignores the probe and never answers."""
    for number in range(1, attempts + 1):
        try:
            await attempt(wav, timeout, min_seconds, ring_app)
            return
        except asyncio.TimeoutError:
            print(f"Probe attempt {number}/{attempts} timed out after {timeout:g}s with no passing risk message", flush=True)
            if number == attempts:
                raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wav", type=Path)
    parser.add_argument("--timeout", type=float, default=240, help="seconds to wait per attempt")
    parser.add_argument("--attempts", type=int, default=1)
    parser.add_argument("--min-seconds", type=float, default=35, help="healthy scoring duration; transcript and voice must both advance")
    parser.add_argument("--ring", action="store_true", help="also invite the simulator and require its microphone speech")
    args = parser.parse_args()
    if not math.isfinite(args.min_seconds) or args.min_seconds < 0 or not math.isfinite(args.timeout) or args.timeout <= args.min_seconds:
        parser.error("timeout must exceed finite nonnegative min-seconds")
    if args.attempts < 1:
        parser.error("--attempts must be at least 1")
    asyncio.run(probe(args.wav, args.timeout, args.attempts, args.min_seconds, args.ring))

