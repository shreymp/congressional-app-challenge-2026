"""Exercise probe dispatch, evidence gating, simulator media and cleanup without a network."""
import asyncio
from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

DEPLOY = Path(__file__).resolve().parents[1] / "deploy/livekit"
LIVE = Path(__file__).resolve().parents[1] / "backend/AI Deepfake Pipeline/LiveKit Setup"
sys.path.insert(0, str(DEPLOY))
sys.path.insert(0, str(LIVE))
spec = importlib.util.spec_from_file_location("calltest_probe", DEPLOY / "probe.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
import senior_ring


class ProbeRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, *, ring_app=False, answered=True, microphone=True, agent=True):
        handlers, background = {}, []
        room = SimpleNamespace(remote_participants={}, local_participant=SimpleNamespace())
        room.on = lambda event: lambda fn: handlers.setdefault(event, fn)
        room.connect = AsyncMock()
        room.disconnect = AsyncMock()
        lk = SimpleNamespace(room=SimpleNamespace(delete_room=AsyncMock()))

        async def dispatch(request):
            room.name = request.room
        lk.agent_dispatch = SimpleNamespace(create_dispatch=AsyncMock(side_effect=dispatch))
        manager = SimpleNamespace(__aenter__=None)
        manager = AsyncMock()
        manager.__aenter__.return_value = lk

        async def emit():
            if ring_app:
                handlers["track_subscribed"](SimpleNamespace(kind=probe.rtc.TrackKind.KIND_AUDIO), None,
                                             SimpleNamespace(identity=senior_ring.SENIOR_IDENTITY))
            for n in range(1, 5):
                await asyncio.sleep(.005)
                message = dict(schema=1, model="real", room=room.name, callerIdentity="backend-probe-caller",
                               streamID="agent-stream", sequence=n, type="risk", infer_ms=1,
                               deepfake={"p_last": .9, "updates": n},
                               transcript={"state": "monitoring", "probability": .8, "age_sec": 0,
                                           "scored_revision": n})
                handlers["data_received"](SimpleNamespace(topic="scam-guard.risk", data=json.dumps(message),
                    participant=SimpleNamespace(kind=4 if agent else 0)))
        async def publish(*args):
            background.append(asyncio.create_task(emit()))
        room.local_participant.publish_track = publish

        async def capture(*args):
            await asyncio.sleep(.001)
        source = SimpleNamespace(capture_frame=capture)

        class Stream:
            def __init__(self, *args, **kwargs):
                self.sent = False
            def __aiter__(self):
                return self
            async def __anext__(self):
                if self.sent:
                    raise StopAsyncIteration
                self.sent = True
                samples = probe.np.full(320, 1000 if microphone else 0, dtype=probe.np.int16)
                return SimpleNamespace(frame=SimpleNamespace(data=samples.tobytes()))
            async def aclose(self):
                pass
        ring = SimpleNamespace(answered=answered, run=AsyncMock())
        try:
            with patch.dict(os.environ, LIVEKIT_URL="wss://test.livekit.cloud", LIVEKIT_API_KEY="test-key",
                            LIVEKIT_API_SECRET="offline-test-secret-at-least-32-bytes"), \
                 patch.object(probe.sf, "read", return_value=(probe.np.ones((1600, 1)), 16000)), \
                 patch.object(probe.rtc, "Room", return_value=room), \
                 patch.object(probe.rtc, "AudioSource", return_value=source), \
                 patch.object(probe.rtc, "AudioStream", Stream), \
                 patch.object(probe.rtc.LocalAudioTrack, "create_audio_track", return_value=object()), \
                 patch.object(probe.api, "LiveKitAPI", return_value=manager), \
                 patch.object(senior_ring, "SeniorRing", return_value=ring), redirect_stdout(io.StringIO()):
                await probe.attempt("unused.wav", .08, min_seconds=0, ring_app=ring_app)
        finally:
            await asyncio.gather(*background, return_exceptions=True)
            room.disconnect.assert_awaited_once()
            lk.room.delete_room.assert_awaited_once()
        return ring

    async def test_backend_dispatch_and_cloud_evidence_pass(self):
        await self.exercise()

    async def test_full_call_requires_answer_and_returning_microphone_audio(self):
        ring = await self.exercise(ring_app=True)
        ring.run.assert_awaited_once()
        for changes in ({"answered": False}, {"microphone": False}):
            with self.assertRaises(asyncio.TimeoutError):
                await self.exercise(ring_app=True, **changes)

    async def test_non_agent_evidence_cannot_pass(self):
        with self.assertRaises(asyncio.TimeoutError):
            await self.exercise(agent=False)


if __name__ == "__main__":
    unittest.main()
