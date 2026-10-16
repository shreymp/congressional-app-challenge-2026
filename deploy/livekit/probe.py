"""Send consented fixture speech through a deployed worker without ringing the app."""
import argparse
import asyncio
from datetime import timedelta
import json
import math
import os
from pathlib import Path
import uuid

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly
from livekit import api, rtc


async def probe(wav, timeout):
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
    summary = {}

    @room.on("data_received")
    def receive(packet):
        if packet.topic != "scam-guard.risk":
            return
        try:
            message = json.loads(packet.data)
            if message.get("schema") != 1 or message.get("model") != "real" or message.get("callerIdentity") != identity or message.get("room") != name:
                return
            text = message.get("transcript") or {}
            voice = message.get("deepfake") or {}
            probability = text.get("probability")
            if (message.get("type") == "risk" and isinstance(voice.get("p_last"), (int, float))
                    and text.get("state") == "monitoring" and type(probability) in (int, float)
                    and math.isfinite(probability) and 0 <= probability <= 1):
                summary.update(model="real", schema=1, deepfake=True, transcript=True,
                               transcript_revision=text.get("scored_revision"), infer_ms=message.get("infer_ms"))
                passed.set()
        except (ValueError, TypeError):
            return

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
            await asyncio.wait_for(passed.wait(), timeout)
            print("BACKEND PROBE PASSED", json.dumps(summary))
        finally:
            if playback:
                playback.cancel()
                await asyncio.gather(playback, return_exceptions=True)
            await room.disconnect()
            await lk.room.delete_room(api.DeleteRoomRequest(room=name))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wav", type=Path)
    parser.add_argument("--timeout", type=float, default=240)
    args = parser.parse_args()
    asyncio.run(probe(args.wav, args.timeout))
