"""No downloaded models or LiveKit credentials required: python -m unittest -v test_transcript_pipeline."""
import asyncio
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from risk import combine
from transcript_pipeline import MAX_CONTEXT_CHARS, TranscriptPipeline, score_http


class Recognizer:
    def __init__(self):
        self.audio = []

    def accept(self, pcm):
        self.audio.append(pcm)
        return "read me the code", False


async def eventually(predicate):
    async with asyncio.timeout(2):
        while not predicate():
            await asyncio.sleep(0.01)


class PipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_partial_revisions_and_final_do_not_duplicate_words(self):
        pipe = TranscriptPipeline(Recognizer(), score=lambda _: 0.9)
        pipe.update("read", False)
        pipe.update("read me", False)
        pipe.update("read me the code", True)
        pipe.update("now", False)
        self.assertEqual(pipe.text, "read me the code now")
        self.assertIsNone(pipe.snapshot()["probability"])
        pipe.update("x" * (MAX_CONTEXT_CHARS * 2), True)
        self.assertEqual(len(pipe.text), MAX_CONTEXT_CHARS)
        await pipe.aclose()
        self.assertEqual(pipe.text, "")

    async def test_excerpt_requires_opt_in_flagged_call_and_final_words(self):
        for enabled in [False, True]:
            pipe = TranscriptPipeline(Recognizer(), score=lambda _: 0.91, every=0.01, save_excerpt=enabled)
            pipe.start()
            try:
                pipe.update("read me the code", False)
                await eventually(lambda: pipe.snapshot()["probability"] is not None)
                self.assertNotIn("saved_excerpt", pipe.snapshot())
                pipe.update("read me the code", True)
                await eventually(lambda: pipe.snapshot()["scored_revision"] == pipe._revision)
                self.assertEqual(pipe.snapshot().get("saved_excerpt"), "read me the code" if enabled else None)
            finally:
                await pipe.aclose()
            self.assertNotIn("saved_excerpt", pipe.snapshot())
        safe = TranscriptPipeline(Recognizer(), score=lambda _: 0.08, save_excerpt=True)
        safe.start()
        try:
            safe.update("see you at dinner", True)
            await eventually(lambda: safe.snapshot()["probability"] is not None)
            self.assertNotIn("saved_excerpt", safe.snapshot())
        finally:
            await safe.aclose()

    async def test_silence_preserved_audio_and_fused_risk(self):
        recognizer, received = Recognizer(), []
        pipe = TranscriptPipeline(recognizer, score=lambda text: received.append(text) or 0.91, every=0.1)
        pipe.start()
        try:
            pcm = b"\x00\x00" * 320  # silence still belongs in the recognizer stream
            pipe.push(pcm)
            await eventually(lambda: pipe.snapshot()["probability"] is not None)
            self.assertEqual(recognizer.audio, [pcm])
            self.assertEqual(received[0], "Caller: read me the code")
            self.assertEqual(combine("high", pipe.snapshot()["probability"]), "prevention")
        finally:
            await pipe.aclose()
        self.assertEqual(pipe._tasks, [])

    async def test_slow_inference_coalesces_latest_context(self):
        entered, release = threading.Event(), threading.Event()
        requests = []

        def score(text):
            requests.append(text)
            if len(requests) == 1:
                entered.set()
                release.wait(2)
            return 0.8

        pipe = TranscriptPipeline(Recognizer(), score=score, every=0.01)
        pipe.start()
        try:
            pipe.update("one", False)
            await eventually(entered.is_set)
            for i in range(20):
                pipe.update(f"newest {i}", False)
            self.assertEqual(len(requests), 1)
            release.set()
            await eventually(lambda: len(requests) >= 2)
            self.assertEqual(requests[1], "Caller: newest 19")
        finally:
            release.set()
            await pipe.aclose()

    async def test_service_failure_clears_old_score_and_retries(self):
        fail = False

        def score(_):
            if fail:
                raise OSError("offline")
            return 0.99

        pipe = TranscriptPipeline(Recognizer(), score=score, every=0.01)
        pipe.start()
        try:
            pipe.update("send money", False)
            await eventually(lambda: pipe.snapshot()["probability"] is not None)
            fail = True
            await eventually(lambda: pipe.snapshot()["state"] == "jev_unavailable")
            self.assertIsNone(pipe.snapshot()["probability"])
            self.assertEqual(combine("high", pipe.snapshot()["probability"]), "high")
            fail = False
            await eventually(lambda: pipe.snapshot()["state"] == "monitoring")
        finally:
            await pipe.aclose()

    async def test_stale_score_and_queue_overrun_cannot_escalate(self):
        now = [10.0]
        pipe = TranscriptPipeline(Recognizer(), score=lambda _: 0.9, max_age=5, max_frames=1,
                                  clock=lambda: now[0])
        pipe.start()
        try:
            pipe.update("send money", False)
            await eventually(lambda: pipe.snapshot()["probability"] is not None)
            now[0] = 20
            self.assertEqual(pipe.snapshot()["state"], "stale")
            self.assertIsNone(pipe.snapshot()["probability"])
            pipe.push(b"a")
            pipe.push(b"b")
            self.assertEqual(pipe.snapshot()["state"], "audio_overrun")
            self.assertIsNone(pipe.snapshot()["probability"])
        finally:
            await pipe.aclose()

    async def test_inflight_result_cannot_revive_overrun(self):
        entered, release = threading.Event(), threading.Event()

        def score(_):
            entered.set()
            release.wait(2)
            return 1.0

        pipe = TranscriptPipeline(Recognizer(), score=score, max_frames=1)
        pipe.start()
        try:
            pipe.update("send money", False)
            await eventually(entered.is_set)
            pipe.push(b"a")
            pipe.push(b"b")
            release.set()
            await asyncio.sleep(0.05)
            self.assertEqual(pipe.snapshot()["state"], "audio_overrun")
            self.assertIsNone(pipe.snapshot()["probability"])
        finally:
            release.set()
            await pipe.aclose()


    async def test_continuous_speech_keeps_score_fresh(self):
        # Words keep arriving while each request is in flight, as on a real call.
        entered, release = threading.Event(), threading.Event()
        calls = []

        def score(text):
            calls.append(text)
            entered.set()
            release.wait(2)
            return 0.7

        pipe = TranscriptPipeline(Recognizer(), score=score, every=0.01)
        pipe.start()
        try:
            pipe.update("send", False)
            await eventually(entered.is_set)
            pipe.update("send money", False)
            entered.clear()
            release.set()
            await eventually(lambda: pipe.snapshot()["state"] == "monitoring")
            self.assertEqual(pipe.snapshot()["probability"], 0.7)
            await eventually(lambda: pipe.snapshot()["scored_revision"] == 2)
        finally:
            release.set()
            await pipe.aclose()

    async def test_withdrawn_context_cannot_revive_inflight_score(self):
        entered, release = threading.Event(), threading.Event()

        def score(_):
            entered.set()
            release.wait(2)
            return 0.9

        pipe = TranscriptPipeline(Recognizer(), score=score)
        pipe.start()
        try:
            pipe.update("send money", False)
            await eventually(entered.is_set)
            pipe.update("", False)          # recognizer withdraws everything
            pipe.update("hello", False)     # new context before the old reply lands
            release.set()
            await asyncio.sleep(0.05)
            self.assertIsNone(pipe.snapshot()["probability"])
            self.assertEqual(pipe.snapshot()["state"], "listening")
        finally:
            release.set()
            await pipe.aclose()


class HttpTests(unittest.TestCase):
    def test_contract_rejects_invalid_probabilities_and_limits_response(self):
        reply = {"probability": 0.82}
        received = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps(reply).encode())

            def log_message(self, *_):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        url = f"http://127.0.0.1:{server.server_port}/v1/jev/probability"
        try:
            self.assertEqual(score_http(url, "hello", 1), 0.82)
            self.assertEqual(received, [{"transcript": "hello"}])
            for invalid in (True, -0.1, 1.1, "0.8", None, float("nan")):
                reply["probability"] = invalid
                with self.assertRaises(ValueError):
                    score_http(url, "hello", 1)
            reply = {"too_large": "x" * 5000}
            with self.assertRaises(ValueError):
                score_http(url, "hello", 1)
        finally:
            server.shutdown()
            server.server_close()
            worker.join()


if __name__ == "__main__":
    unittest.main()
