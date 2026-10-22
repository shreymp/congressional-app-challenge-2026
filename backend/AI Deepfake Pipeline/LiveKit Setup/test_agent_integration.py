"""Production agent orchestration with fake rooms/audio. Never connects to LiveKit."""
import asyncio
import json
import threading
import types
import unittest
from unittest.mock import patch

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
    def context(self, detector):
        room = FakeRoom()
        async def caller(**kwargs):
            self.assertEqual(kwargs["kind"], agent.rtc.ParticipantKind.PARTICIPANT_KIND_SIP)
            return types.SimpleNamespace(identity="sip-test", attributes={})
        return types.SimpleNamespace(room=room, proc=types.SimpleNamespace(userdata={"detector": detector}),
                                     wait_for_participant=caller, add_shutdown_callback=lambda callback: None)

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

    async def test_saved_excerpt_is_sent_only_to_senior(self):
        class TextPipeline:
            def start(self): pass
            def push(self, data): pass
            def snapshot(self):
                return {"state": "monitoring", "probability": .95, "saved_excerpt": "read me the code"}
            async def aclose(self): pass
        ctx, stream = self.context(FakeDetector()), FakeStream()
        ctx.proc.userdata["stt_model"] = object()
        with patch.object(agent.transcript_pipeline, "for_call", return_value=TextPipeline()), patch.object(agent.rtc.AudioStream, "from_participant", return_value=stream):
            await asyncio.wait_for(agent._score_call(ctx), 3)
        self.assertTrue(ctx.room.messages)
        for message, options in ctx.room.messages:
            self.assertEqual(message["transcript"]["saved_excerpt"], "read me the code")
            self.assertEqual(options["destination_identities"], [agent.senior_ring.SENIOR_IDENTITY])

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

