"""Ring the senior's app with NO phone call: ring -> answer -> two-way audio -> caller hangs up.

A fake caller joins a throwaway room (not a call-* room, so scam-guard is not dispatched) and
plays quiet beeps as its microphone. Then the same code the agent uses (senior_ring.SeniorRing)
invites the senior's app through the lobby. Open the app on the iPhone first.

Usage (from the LiveKit Setup folder, venv active):
  python tools/test_ring.py
  python tools/test_ring.py --handle +13125550123 --duration 300

What to check
  - the phone shows the incoming call with the --handle number; this prints "senior joined";
  - while it rings the senior must NOT count as answered, although the caller's beeps are
    already published (a real phone caller publishes while ringing too);
  - answer on the phone: this prints "senior answered", you hear the beeps on the phone, and
    the level meter below moves when you talk into the phone (two-way audio);
  - Ctrl+C here = the caller hangs up: the app should end the call on its own;
  - hang up on the phone instead: after a few seconds the room is deleted, as the agent does;
  - do not answer: after RING_TIMEOUT_SEC the no-answer stub is logged.
"""
import argparse
import asyncio
import logging
import math
import os
import sys
import time
from datetime import datetime, timedelta

import numpy as np
from dotenv import load_dotenv
from livekit import api, rtc

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(HERE, ".env.local"))
sys.path.insert(0, HERE)

import senior_ring  # noqa: E402  (needs the folder above on sys.path)

TONE_SR = 48000
FRAME = TONE_SR // 50            # 20 ms


def beep_pattern() -> np.ndarray:
    """One second of int16 audio: a quiet 0.4 s beep (440 Hz), then silence."""
    n = int(0.4 * TONE_SR)
    t = np.arange(n) / TONE_SR
    fade = np.minimum(1.0, np.minimum(t, t[::-1]) / 0.01)          # 10 ms in/out, no clicks
    beep = 0.08 * np.sin(2 * np.pi * 440 * t) * fade
    out = np.zeros(TONE_SR, dtype=np.float32)
    out[:n] = beep
    return (out * 32767).astype(np.int16)


async def play_beeps(source: rtc.AudioSource) -> None:
    """Feed the pattern in 20 ms frames at real-time pace until cancelled."""
    pattern, pos = beep_pattern(), 0
    loop = asyncio.get_running_loop()
    next_t = loop.time()
    try:
        while True:
            chunk = pattern[pos:pos + FRAME]
            await source.capture_frame(rtc.AudioFrame(chunk.tobytes(), TONE_SR, 1, len(chunk)))
            pos = (pos + FRAME) % len(pattern)
            next_t += FRAME / TONE_SR
            await asyncio.sleep(max(0.0, next_t - loop.time()))
    except Exception as e:           # say so: otherwise the senior just hears nothing on answer
        print(f"beep playback stopped: {e!r}")


def level_db(pcm: np.ndarray) -> float:
    """RMS level of int16 audio in dBFS (0 = full scale). Silence gives -inf."""
    if len(pcm) == 0:
        return -math.inf
    rms = float(np.sqrt(np.mean((pcm.astype(np.float32) / 32768.0) ** 2)))
    return 20 * math.log10(rms) if rms > 0 else -math.inf


async def level_meter(track: rtc.Track, seen: dict) -> None:
    """Print the level of the senior's microphone once per second."""
    stream = rtc.AudioStream(track, sample_rate=16000, num_channels=1)
    buf: list[np.ndarray] = []
    t_last = time.monotonic()
    try:
        async for event in stream:
            buf.append(np.frombuffer(event.frame.data, dtype=np.int16).copy())
            if time.monotonic() - t_last >= 1.0:
                db = level_db(np.concatenate(buf))
                buf, t_last = [], time.monotonic()
                if db > -50:
                    seen["voice"] = True
                bar = "#" * max(0, int((db + 60) / 2)) if db > -60 else ""
                print(f"    senior mic {db:6.1f} dBFS  {bar}")
    finally:
        await stream.aclose()


async def main(a: argparse.Namespace) -> None:
    room_name = f"ringtest-{datetime.now():%Y%m%d-%H%M%S}"
    token = (api.AccessToken()
             .with_identity(a.caller_identity)
             .with_name("Ring test caller")
             .with_ttl(timedelta(hours=1))
             .with_grants(api.VideoGrants(room_join=True, room=room_name))
             .to_jwt())

    room = rtc.Room()
    tasks: list[asyncio.Task] = []
    seen = {"voice": False}

    @room.on("track_subscribed")
    def _on_track(track: rtc.Track, publication, participant) -> None:
        if participant.identity == senior_ring.SENIOR_IDENTITY and track.kind == rtc.TrackKind.KIND_AUDIO:
            tasks.append(asyncio.create_task(level_meter(track, seen)))

    await room.connect(os.environ["LIVEKIT_URL"], token)
    print(f"room {room_name}: fake caller \"{a.caller_identity}\" joined, number shown to the app {a.handle!r}")
    ring = None
    try:
        # Publish right away, like a real phone caller does while it is still ringing.
        source = rtc.AudioSource(TONE_SR, 1)
        track = rtc.LocalAudioTrack.create_audio_track("ring-test-beeps", source)
        await room.local_participant.publish_track(
            track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE))
        tasks.append(asyncio.create_task(play_beeps(source)))
        print(f"playing beeps. Ctrl+C = the caller hangs up. Stops by itself after {a.duration:.0f}s.")

        async with api.LiveKitAPI() as lk:
            ring = senior_ring.SeniorRing(
                lk=lk, room=room, caller_identity=a.caller_identity, caller_is_local=True,
                handle=a.handle,
                delete_room=lambda: lk.room.delete_room(api.DeleteRoomRequest(room=room_name)))
            try:
                outcome = await asyncio.wait_for(ring.run(), timeout=a.duration)
            except asyncio.TimeoutError:
                outcome = f"--duration {a.duration:.0f}s is over, the fake caller hangs up"
            print(f"stopped: {outcome}")
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await room.disconnect()                 # the fake caller leaves: the app should end the call
        if ring is not None:
            print(f"summary: senior joined={ring.joined}  answered={ring.answered}  "
                  f"audio heard from the senior's microphone={seen['voice']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--handle", default="+15555550100", help="fake caller number shown on the phone")
    ap.add_argument("--caller-identity", default="test-caller", help="identity of the fake caller")
    ap.add_argument("--duration", type=float, default=120, help="seconds before the fake caller hangs up")
    args = ap.parse_args()

    missing = [k for k in ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET") if not os.environ.get(k)]
    if missing:
        sys.exit(f"Not set: {', '.join(missing)}. Fill in {os.path.join(HERE, '.env.local')} "
                 "(copy .env.example; the values are in LiveKit Cloud -> Settings -> API keys).")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
    try:
        asyncio.run(main(args))
    except KeyboardInterrupt:
        pass
