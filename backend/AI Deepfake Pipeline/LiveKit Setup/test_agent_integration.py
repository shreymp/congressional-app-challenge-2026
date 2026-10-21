"""Production agent orchestration with fake rooms/audio. Never connects to LiveKit."""
import asyncio
import json
import threading
import types
import unittest
from unittest.mock import AsyncMock, patch

import numpy as np
import agent


class FakeDetector:
    mode = "real"
    meta = {"window_sec": 4.0, "threshold_eer": .9, "threshold_1pct_fpr": .99}

    def score_window(self, audio):
        return {"p_fake": .999, "logit": 7.0, "infer_ms": 1}


class FakeRoom:
    name = "call-test"
    def __init__(self):
        self.messages = []
        self.connected = True
        self.local_participant = self

    def isconnected(self):
        return self.connected

    async def publish_data(self, payload, **kwargs):
        self.messages.append((json.loads(payload), kwargs))


class FakeStream:
    def __init__(self, hold=False):
        self.closed = False
        self.hold = hold
        self.waiting = asyncio.Event()
        self.frame = np.full(320, 5000, dtype=np.int16).tobytes()

    async def __aiter__(self):
        for _ in range(170):
            await asyncio.sleep(0)
            yield types.SimpleNamespace(frame=types.SimpleNamespace(data=self.frame))
        if self.hold:
            self.waiting.set()
            await asyncio.Event().wait()
        else:
            await asyncio.sleep(.05)  # let the worker finish before audio closes

    async def aclose(self):
        self.closed = True


class AgentIntegrationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.notice_patch = patch.object(agent, "play_recording_notice", new_callable=AsyncMock)
        self.notice = self.notice_patch.start()
        self.addCleanup(self.notice_patch.stop)

    def context(self, detector):
        room = FakeRoom()
        async def caller(**kwargs):
            self.assertEqual(kwargs["kind"], agent.rtc.ParticipantKind.PARTICIPANT_KIND_SIP)
            return types.SimpleNamespace(identity="sip-test", attributes={})
        return types.SimpleNamespace(room=room, proc=types.SimpleNamespace(userdata={"detector": detector}),
                                     wait_for_participant=caller, add_shutdown_callback=lambda callback: None)

    async def test_notice_blocks_transcription_audio_and_recording_until_playback_finishes(self):
        ctx, stream = self.context(FakeDetector()), FakeStream()
        ctx.proc.userdata["stt_model"] = object()
        started, release = asyncio.Event(), asyncio.Event()
        async def play(room):
            started.set()
            await release.wait()
        self.notice.side_effect = play
        with patch.object(agent.transcript_pipeline, "for_call", side_effect=RuntimeError("test STT disabled")) as stt, \
             patch.object(agent.rtc.AudioStream, "from_participant", return_value=stream) as audio, \
             patch.object(agent, "_save_wav") as save, patch.object(agent, "RECORD", True):
            task = asyncio.create_task(agent._score_call(ctx))
            try:
                await asyncio.wait_for(started.wait(), 1)
                stt.assert_not_called()
                audio.assert_not_called()
                save.assert_not_called()
                release.set()
                with self.assertLogs("scam-guard", level="ERROR"):
                    await asyncio.wait_for(task, 3)
                stt.assert_called_once()
                audio.assert_called_once()
                save.assert_called_once()
                self.notice.assert_awaited_once_with(ctx.room)
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    async def test_failed_or_timed_out_notice_never_opens_processing_stream(self):
        for failure in (RuntimeError("missing announcement"), asyncio.TimeoutError()):
            ctx = self.context(FakeDetector())
            ctx.proc.userdata["stt_model"] = object()
            self.notice.side_effect = failure
            with patch.object(agent.transcript_pipeline, "for_call") as stt, \
                 patch.object(agent.rtc.AudioStream, "from_participant") as audio, \
                 patch.object(agent, "_save_wav") as save, patch.object(agent, "RECORD", True):
                with self.assertLogs("scam-guard", level="ERROR"):
                    await agent._score_call(ctx)
                stt.assert_not_called()
                audio.assert_not_called()
                save.assert_not_called()
                self.assertEqual(ctx.room.messages[0][0]["reason"], "recording_notice_failed")

    async def test_backend_probe_skips_notice(self):
        ctx, stream = self.context(FakeDetector()), FakeStream()
        ctx.wait_for_participant = AsyncMock(return_value=types.SimpleNamespace(identity="backend-probe-caller", attributes={}))
        with patch.object(agent, "_probe_diag", return_value={}), \
             patch.object(agent.rtc.AudioStream, "from_participant", return_value=stream):
            await agent._score_call(ctx, probe=True)
        self.notice.assert_not_awaited()
        ctx.wait_for_participant.assert_awaited_once_with(identity="backend-probe-caller")

    async def test_notice_timeout_cancels_playback_and_preserves_ring_supervisor(self):
        ctx = self.context(FakeDetector())
        ctx.connect = AsyncMock()
        ctx.job = types.SimpleNamespace(metadata="")
        cancelled = asyncio.Event()
        async def stalled(room):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        self.notice.side_effect = stalled
        with patch.object(agent, "NOTICE_TIMEOUT_SEC", .01), \
             patch.object(agent.senior_ring, "start_for_job") as ring, \
             patch.object(agent.rtc.AudioStream, "from_participant") as audio:
            with self.assertLogs("scam-guard", level="ERROR"):
                await asyncio.wait_for(agent.scam_guard(ctx), 1)
            ring.assert_called_once_with(ctx)
            audio.assert_not_called()
            self.assertTrue(cancelled.is_set())

    async def test_scores_and_publishes_versioned_caller_evidence_then_closes(self):
        ctx, stream = self.context(FakeDetector()), FakeStream()
        with patch.object(agent.rtc.AudioStream, "from_participant", return_value=stream), patch.object(agent, "SCORE_EVERY_SEC", 0):
            await asyncio.wait_for(agent._score_call(ctx), 3)
        self.assertTrue(stream.closed)
        risks = [m for m, _ in ctx.room.messages if m["type"] == "risk"]
        self.assertTrue(risks)
        self.assertEqual(risks[0]["callerIdentity"], "sip-test")
        self.assertEqual(risks[0]["model"], "real")
        self.assertEqual(risks[0]["schema"], 1)
        sequences = [m["sequence"] for m, _ in ctx.room.messages]
        self.assertEqual(sequences, sorted(set(sequences)))
        self.assertTrue(all(k["topic"] == "scam-guard.risk" and k["reliable"] for _, k in ctx.room.messages))
        count = len(ctx.room.messages)
        await asyncio.sleep(.05)
        self.assertEqual(len(ctx.room.messages), count)

    async def test_transcript_is_fused_into_versioned_risk_updates(self):
        class TextPipeline:
            def __init__(self): self.frames = 0; self.closed = False
            def start(self): pass
            def push(self, data): self.frames += 1
            def snapshot(self): return {"state": "monitoring", "probability": .95, "revision": self.frames}
            async def aclose(self): self.closed = True
        text = TextPipeline()
        ctx, stream = self.context(FakeDetector()), FakeStream()
        ctx.proc.userdata["stt_model"] = object()
        with patch.object(agent.transcript_pipeline, "for_call", return_value=text), patch.object(agent.rtc.AudioStream, "from_participant", return_value=stream), patch.object(agent, "SCORE_EVERY_SEC", 0):
            await asyncio.wait_for(agent._score_call(ctx), 3)
        self.assertEqual(text.frames, 170)
        self.assertTrue(text.closed)
        risks = [m for m, _ in ctx.room.messages if m["type"] == "risk"]
        self.assertTrue(risks)
        self.assertTrue(all(m["transcript"]["probability"] == .95 for m in risks))
        self.assertTrue(all(m["level"] == agent.combine(m["deepfake"]["level"], .95) for m in risks))

    async def test_transcription_continues_when_voice_model_is_missing(self):
        class TextPipeline:
            frames = 0
            def start(self): pass
            def push(self, data): self.frames += 1
            def snapshot(self): return {"state": "monitoring", "probability": .5}
            async def aclose(self): pass
        text = TextPipeline()
        ctx, stream = self.context(None), FakeStream()
        ctx.proc.userdata["stt_model"] = object()
        with patch.object(agent.transcript_pipeline, "for_call", return_value=text), patch.object(agent.rtc.AudioStream, "from_participant", return_value=stream):
            await asyncio.wait_for(agent._score_call(ctx), 3)
        self.assertEqual(text.frames, 170)
        self.assertTrue(stream.closed)
        self.assertEqual(ctx.room.messages[0][0]["state"], "unavailable")
        self.assertEqual(ctx.room.messages[0][0]["transcript"]["probability"], .5)

    async def test_failed_model_load_reports_unavailable_and_can_be_cancelled(self):
        ctx = self.context(None)
        task = asyncio.create_task(agent._score_call(ctx))
        await asyncio.sleep(.02)
        self.assertEqual(ctx.room.messages[0][0]["state"], "unavailable")
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

    async def test_cancellation_stops_inflight_inference_from_publishing(self):
        release = threading.Event()
        started = threading.Event()
        class SlowDetector(FakeDetector):
            def score_window(self, audio):
                started.set()
                release.wait(3)
                return super().score_window(audio)
        ctx, stream = self.context(SlowDetector()), FakeStream(hold=True)
        try:
            with patch.object(agent.rtc.AudioStream, "from_participant", return_value=stream), patch.object(agent, "SCORE_EVERY_SEC", 0):
                task = asyncio.create_task(agent._score_call(ctx))
                await asyncio.wait_for(stream.waiting.wait(), 3)
                for _ in range(100):
                    if started.is_set(): break
                    await asyncio.sleep(.001)
                self.assertTrue(started.is_set())
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
            self.assertTrue(stream.closed)
            count = len(ctx.room.messages)
            release.set()
            await asyncio.sleep(.05)
            self.assertEqual(len(ctx.room.messages), count)
        finally:
            release.set()

    async def test_failed_inference_does_not_fail_call_or_leak_stream(self):
        class BrokenDetector(FakeDetector):
            def score_window(self, audio):
                raise ValueError("test inference failure")
        ctx, stream = self.context(BrokenDetector()), FakeStream()
        with patch.object(agent.rtc.AudioStream, "from_participant", return_value=stream), patch.object(agent, "SCORE_EVERY_SEC", 0):
            with self.assertLogs("scam-guard", level="ERROR"):
                await asyncio.wait_for(agent._score_call(ctx), 3)
        self.assertTrue(stream.closed)
        self.assertTrue(any(m.get("state") == "unavailable" for m, _ in ctx.room.messages))


if __name__ == "__main__":
    unittest.main()

