"""Live and file replay share this audio-to-assessment path; no LiveKit imports."""
from __future__ import annotations

import math

from audio_window import VoicedWindow
from risk import CallEvidenceEngine, combine


class AudioScoringSession:
    # Clear stale rolling AUDIO after a pause, never accumulated call evidence.
    SILENCE_SEC = 6.0
    INFERENCE_TIMEOUT_SEC = 10.0

    def __init__(self, detector, thresholds: tuple[float, float], sample_rate=16000):
        self.detector = detector
        self.thresholds = thresholds
        self.sample_rate = sample_rate
        self.window = VoicedWindow(sample_rate=sample_rate, window_sec=detector.meta["window_sec"])
        self.risk = CallEvidenceEngine(*thresholds)
        self.last_speech = None
        self.last_scored_samples = 0
        self.pending_since = None
        self.generation = 0
        self.pending_weight = 1.0
        self.latest = {"type": "status", "state": "analyzing"}

    def push(self, pcm, now: float) -> None:
        self.refresh(now)
        if self.window.push_int16(pcm):
            self.last_speech = now

    def refresh(self, now: float) -> None:
        if self.last_speech is not None and now - self.last_speech >= self.SILENCE_SEC:
            self.window.filled = 0
            self.last_speech = None

    def snapshot(self, now: float):
        self.refresh(now)
        if (not self.window.ready() or self.window.total_seen - self.last_scored_samples < self.window.capacity
                or self.pending_since is not None):
            return None
        self.last_scored_samples = self.window.total_seen
        self.pending_since = now
        self.pending_weight = self.window.weight
        self.generation += 1
        return self.window.snapshot(), self.generation

    def complete(self, result: dict, generation: int) -> None:
        if generation != self.generation or self.pending_since is None:
            return
        self.pending_since = None
        p, z, ms = float(result["p_fake"]), float(result["logit"]), float(result["infer_ms"])
        if not (0 <= p <= 1 and math.isfinite(z) and math.isfinite(ms) and ms >= 0):
            raise ValueError("Detector returned invalid evidence")
        state = self.risk.update(p, z, self.pending_weight)
        self.latest = {"type": "risk", "level": combine(state["level"], None),
                       "deepfake": state, "transcript": None, "infer_ms": round(ms, 1),
                       "voiced_sec": round(self.window.total_voiced / self.sample_rate, 1)}

    def failed(self) -> None:
        self.pending_since = None
        self.latest = {"type": "status", "state": "unavailable"}

    def payload(self, now: float) -> dict:
        self.refresh(now)
        if self.pending_since is not None:
            if now - self.pending_since >= self.INFERENCE_TIMEOUT_SEC:
                return {"type": "status", "state": "unavailable"}
            if self.latest.get("type") != "risk":
                return {"type": "status", "state": "analyzing"}
        return dict(self.latest)
