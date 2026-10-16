"""Bounded, per-call caller PCM -> Vosk -> JEV pipeline. No transcripts are logged.

The audio consumer and HTTP scorer run independently of deepfake inference and ringing.
Partial hypotheses replace each other; only final utterances are appended. One HTTP
request at a time scores the newest context, never an accumulating request queue.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import time
import urllib.request
from pathlib import Path
from typing import Callable

log = logging.getLogger("scam-guard.transcript")
MAX_CONTEXT_CHARS = 6000  # <=24 KB UTF-8, below the connector's 32 KB body limit


def env_seconds(name: str, default: float, low: float = 0.1, high: float = 300) -> float:
    try:
        value = float(os.environ.get(name, default))
        if math.isfinite(value) and low <= value <= high:
            return value
    except ValueError:
        pass
    log.warning("invalid %s; using %s seconds", name, default)
    return default


def load_model():
    """Load once in prewarm; recognizers remain isolated per call. Never auto-download."""
    if os.environ.get("TRANSCRIPT_ENABLED", "1") == "0":
        return None
    path = os.environ.get("VOSK_MODEL_PATH", "")
    if not path:
        raise ValueError("VOSK_MODEL_PATH is required for transcription")
    resolved = Path(path).expanduser()
    if not resolved.is_absolute():
        resolved = Path(__file__).resolve().parent / resolved
    if not resolved.is_dir():
        raise ValueError("VOSK_MODEL_PATH does not point to a downloaded model directory")
    from vosk import Model
    return Model(str(resolved))


class VoskRecognizer:
    def __init__(self, model):
        from vosk import KaldiRecognizer
        self._recognizer = KaldiRecognizer(model, 16000)

    def accept(self, pcm: bytes) -> tuple[str, bool]:
        final = self._recognizer.AcceptWaveform(pcm)
        result = json.loads(self._recognizer.Result() if final else self._recognizer.PartialResult())
        return result.get("text" if final else "partial", ""), bool(final)


def score_http(url: str, transcript: str, timeout: float) -> float:
    payload = json.dumps({"transcript": transcript}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=payload, method="POST",
                                     headers={"Content-Type": "application/json"})
    # Local connector by default. HTTP runs off the event loop with a socket timeout.
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read(4097)
    if len(raw) > 4096:
        raise ValueError("oversized JEV response")
    result = json.loads(raw)
    p = result.get("probability") if isinstance(result, dict) else None
    if type(p) not in (int, float) or not math.isfinite(p) or not 0 <= p <= 1:
        raise ValueError("JEV returned an invalid probability")
    return float(p)


class TranscriptPipeline:
    def __init__(self, recognizer, *, score: Callable[[str], float],
                 every: float = 2.5, max_age: float = 15, max_frames: int = 100,
                 clock: Callable[[], float] = time.monotonic):
        self.recognizer, self._score = recognizer, score
        self.every, self.max_age, self.clock = every, max_age, clock
        self._frames: asyncio.Queue[bytes] = asyncio.Queue(maxsize=max_frames)
        self._changed = asyncio.Event()
        self._final = ""
        self._partial = ""
        self._revision = 0
        self._scored_revision = 0
        self._probability: float | None = None
        self._scored_at: float | None = None
        self._state = "listening"
        self._closed = False
        self._audio_failed = False
        self._tasks: list[asyncio.Task] = []

    def start(self) -> None:
        self._tasks = [asyncio.create_task(self._consume_audio(), name="caller_stt"),
                       asyncio.create_task(self._score_latest(), name="caller_jev")]

    def push(self, pcm: bytes | memoryview) -> None:
        """Called from the audio loop; never waits for Vosk, HTTP or a full queue."""
        if self._closed or self._audio_failed:
            return
        try:
            self._frames.put_nowait(bytes(pcm))
        except asyncio.QueueFull:
            # Missing PCM could change words. Stop this branch rather than report a stale verdict.
            self._audio_failed = True
            self._state, self._probability = "audio_overrun", None
            log.warning("transcript audio queue full; transcript scoring disabled for this call")

    @property
    def text(self) -> str:
        return (self._final + " " + self._partial).strip()[-MAX_CONTEXT_CHARS:]

    def update(self, text: str, final: bool) -> None:
        before = self.text
        text = " ".join(text.split())
        if final:
            self._final = (self._final + " " + text).strip()[-MAX_CONTEXT_CHARS:]
            self._partial = ""
        else:
            self._partial = text[-MAX_CONTEXT_CHARS:]
        if self.text != before:
            self._revision += 1
            # Never retain a score after the recognizer withdraws all available context.
            if not self.text:
                self._probability, self._scored_at = None, None
                self._state = "listening"
            self._changed.set()

    def snapshot(self) -> dict:
        age = None if self._scored_at is None else self.clock() - self._scored_at
        state, p = self._state, self._probability
        if p is not None and age is not None and age > self.max_age:
            state, p = "stale", None
        return {"state": state, "probability": p, "revision": self._revision,
                "scored_revision": self._scored_revision,
                "age_sec": None if age is None else round(age, 2), "chars": len(self.text)}

    async def _consume_audio(self) -> None:
        try:
            while not self._audio_failed:
                chunks = [await self._frames.get()]
                # Batch already buffered frames to reduce thread scheduling overhead.
                while len(chunks) < 10 and not self._frames.empty():
                    chunks.append(self._frames.get_nowait())
                text, final = await asyncio.to_thread(self.recognizer.accept, b"".join(chunks))
                if not self._audio_failed:
                    self.update(text, final)
        except Exception:
            self._audio_failed = True
            self._state, self._probability = "stt_unavailable", None
            log.warning("speech recognition stopped; deepfake scoring continues")

    async def _score_latest(self) -> None:
        next_score = 0.0
        while True:
            await self._changed.wait()
            await asyncio.sleep(max(0, next_score - self.clock()))
            self._changed.clear()
            if self._audio_failed or not self.text:
                continue
            text, revision = self.text, self._revision
            try:
                probability = await asyncio.to_thread(self._score, "Caller: " + text)
                # A withdrawn hypothesis / failed audio stream must not revive an old score.
                if not self._audio_failed and self.text and revision == self._revision:
                    self._probability = probability
                    self._scored_at = self.clock()
                    self._scored_revision = revision
                    self._state = "monitoring"
            except Exception:
                if not self._audio_failed:
                    self._state, self._probability = "jev_unavailable", None
                    log.warning("transcript inference unavailable; deepfake scoring continues")
            next_score = self.clock() + self.every
            # Retry unchanged context after a transient connector failure, and refresh scores
            # before they expire during a pause in speech. This is still one bounded request.
            if self.text and not self._audio_failed:
                self._changed.set()

    async def aclose(self) -> None:
        self._closed = True
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        while not self._frames.empty():
            self._frames.get_nowait()
        self._final = self._partial = ""
        self._probability = None


def for_call(model) -> TranscriptPipeline:
    url = os.environ.get("TRANSCRIPT_SCORE_URL", "http://127.0.0.1:3000/v1/jev/probability")
    timeout = env_seconds("TRANSCRIPT_SCORE_TIMEOUT_SEC", 4)
    return TranscriptPipeline(VoskRecognizer(model), score=lambda text: score_http(url, text, timeout),
                              every=env_seconds("TRANSCRIPT_SCORE_EVERY_SEC", 2.5),
                              max_age=env_seconds("TRANSCRIPT_MAX_AGE_SEC", 15))
