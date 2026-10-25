"""Shared real-time/replay scoring; timestamps never refresh on heartbeat receipt."""
from __future__ import annotations

import math

from audio_window import VoicedWindow
from current_evidence import CurrentEvidenceEngine
from pipeline_config import ScoringConfig
from risk import CallEvidenceEngine, combine


class AudioScoringSession:
    SILENCE_SEC = 6.0
    INFERENCE_TIMEOUT_SEC = 10.0

    def __init__(self, detector, thresholds: tuple[float, float], sample_rate=16000,
                 *, config=None, clock_origin=None):
        self.detector, self.thresholds, self.sample_rate = detector, thresholds, sample_rate
        self.config = config or ScoringConfig()
        self.clock_origin = clock_origin
        self.window = VoicedWindow(sample_rate=sample_rate, window_sec=detector.meta["window_sec"],
                                   gate_mode=self.config.gate,
                                   digital_silence_max_sec=self.config.digital_silence_max_sec)
        # Optional Platt calibration (calibration.json next to the checkpoint); None keeps
        # the threshold-derived heuristic center/scale.
        calibration = getattr(detector, "calibration", None)
        self.risk = CallEvidenceEngine(*thresholds, calibration=calibration)
        self.current = CurrentEvidenceEngine(*thresholds, calibration=calibration, horizon_sec=self.config.horizon_sec,
            mode=self.config.current_mode, min_usable_sec=self.config.min_usable_sec,
            entry_usable_sec=self.config.entry_usable_sec, recovery_usable_sec=self.config.recovery_usable_sec,
            warning_usable_sec=self.config.warning_usable_sec, half_life_sec=self.config.half_life_sec)
        self.last_speech = None
        self.last_scored_samples = 0
        self.pending_since = None
        self.generation = 0
        self.pending_weight = 1.0
        self.pending_interval = None
        self.latest = {"type": "status", "state": "analyzing"}
        self.last_now = None
        self.failure_reason = None
        self.closed = False
        self.timing = {}
        self.legacy_events = []
        self._legacy_warning = False
        self.counters = {"submissions": 0, "completions": 0, "failures": 0,
                         "timeouts": 0, "ignored_completions": 0, "publications": 0}

    def _time(self, now):
        if not math.isfinite(now):
            raise ValueError("Nonfinite session clock")
        if self.clock_origin is None:
            self.clock_origin = 0.0
        return max(0.0, now - self.clock_origin)

    def push(self, pcm, now: float) -> None:
        if self.closed:
            return
        self.last_now = now
        self.refresh(now)
        self.timing.setdefault("first_caller_audio_sec", self._time(now))
        if self.window.push_int16(pcm):
            self.last_speech = now
        if self.window.ready():
            self.timing.setdefault("sufficient_speech_sec", self._time(now))

    def refresh(self, now: float) -> None:
        self.last_now = now
        if self.last_speech is not None and now - self.last_speech >= self.SILENCE_SEC:
            self.window.reset_audio()
            self.last_speech = None

    def snapshot(self, now: float):
        self.refresh(now)
        if (self.closed or not self.window.ready()
                or self.window.total_seen - self.last_scored_samples < self.window.capacity
                or self.pending_since is not None):
            return None
        self.last_scored_samples = self.window.total_seen
        self.pending_since = now
        self.pending_weight = self.window.weight
        end = self._time(now)
        self.pending_interval = (max(0.0, end - self.window.capacity / self.sample_rate), end)
        self.generation += 1
        self.failure_reason = None
        self.counters["submissions"] += 1
        self.timing["submission_sec"] = end
        return self.window.snapshot(), self.generation

    def complete(self, result: dict, generation: int, now=None) -> bool:
        if self.closed or generation != self.generation or self.pending_since is None:
            self.counters["ignored_completions"] += 1
            return False
        now = self.last_now if now is None else now
        # Timed-out work is retired when it actually returns. Never queue concurrent work
        # against an uncancellable inference thread, nor count late results as fresh evidence.
        if now - self.pending_since >= self.INFERENCE_TIMEOUT_SEC:
            self.failed("inference_timeout", generation=generation)
            return False
        p, z, ms = float(result["p_fake"]), float(result["logit"]), float(result["infer_ms"])
        if not (math.isfinite(p) and 0 <= p <= 1 and math.isfinite(z) and math.isfinite(ms) and ms >= 0):
            raise ValueError("Detector returned invalid evidence")
        state = self.risk.update(p, z, self.pending_weight)
        start, end = self.pending_interval
        warning = state["recent_ai"]
        if warning:
            if not self._legacy_warning:
                self.legacy_events.append({"id": str(self.generation), "start_sec": start,
                                           "end_sec": end, "current": True})
                self.legacy_events = self.legacy_events[-64:]
            else:
                self.legacy_events[-1]["end_sec"] = end
        elif self._legacy_warning:
            self.legacy_events[-1]["current"] = False
        self._legacy_warning = warning
        if end > start:
            self.current.update(p, z, self.pending_weight, start_sec=start, end_sec=end)
        self.pending_since = None
        self.failure_reason = None
        self.counters["completions"] += 1
        self.timing["completion_sec"] = self._time(now)
        self.latest = {"type": "risk", "level": combine(state["level"], None),
                       "deepfake": state, "transcript": None, "infer_ms": round(ms, 1),
                       "voiced_sec": round(self.window.total_voiced / self.sample_rate, 1),
                       "voiced_sec_kind": "gate_estimate"}
        return True

    def failed(self, reason="inference_failed", generation=None) -> None:
        if generation is not None and generation != self.generation:
            return
        self.pending_since = None
        self.generation += 1
        self.failure_reason = reason
        self.counters["failures"] += 1
        if reason == "inference_timeout":
            self.counters["timeouts"] += 1
        # Preserve last successful evidence for dated history/details.

    def close(self):
        self.closed = True
        self.generation += 1
        self.pending_since = None

    def published(self, now):
        self.counters["publications"] += 1
        self.timing["publication_sec"] = self._time(now)

    def payload(self, now: float) -> dict:
        self.refresh(now)
        current = self.current.snapshot(self._time(now))
        status_reason = self.failure_reason
        timed_out = self.pending_since is not None and now - self.pending_since >= self.INFERENCE_TIMEOUT_SEC
        if timed_out:
            status_reason = "inference_timeout"
        elif self.pending_since is not None:
            status_reason = "inference_pending"
        elif current["freshness"] == "stale":
            status_reason = "evidence_stale"
        quality = self.window.rejection_reason
        status = ("unavailable" if timed_out or self.failure_reason else
                  "stale" if current["freshness"] == "stale" else
                  "available" if self.latest.get("type") == "risk" else "analyzing")
        if status_reason is None and status == "analyzing":
            status_reason = "insufficient_speech"
        assessment = {"current_state": current["state"], "current_score": current["score"],
            "whole_call_score": self.latest.get("deepfake", {}).get("score"),
            "evidence_start_sec": current["evidence_start_sec"], "evidence_end_sec": current["evidence_end_sec"],
            "evidence_age_sec": current["evidence_age_sec"], "freshness": current["freshness"],
            "analysis_status": status, "quality_reason": quality, "status_reason": status_reason,
            "current_warning": bool((current["recent_ai"] if self.config.current_enabled else
                                     self.latest.get("deepfake", {}).get("recent_ai", False))
                                    and current["freshness"] == "fresh"),
            "historical_warning_events": (current["historical_warning_events"] if self.config.current_enabled else
                [dict(event, current=bool(self._legacy_warning and current["freshness"] == "fresh"
                                         and index == len(self.legacy_events)-1))
                 for index, event in enumerate(self.legacy_events)]),
            "pending_state": current["pending_state"], "score_kind": "heuristic"}
        if status == "unavailable":
            payload = {"type": "status", "state": "unavailable", "reason": status_reason}
            if "deepfake" in self.latest:
                payload["previous_deepfake"] = self.latest["deepfake"]
        else:
            payload = dict(self.latest)
        if self.config.current_enabled and status == "stale":
            payload = {"type": "status", "state": "analyzing", "reason": "evidence_stale",
                       "previous_deepfake": self.latest.get("deepfake")}
        if self.config.current_enabled and payload.get("type") == "risk":
            payload["deepfake"] = {**payload["deepfake"], **current, "method": "call-evidence-v2"}
            payload["level"] = current["level"]
        return {**payload, "window_id": self.generation, "evidence_version": "call-evidence-v2",
                "scoring_method": "call-evidence-v2" if self.config.current_enabled else "call-evidence-v1",
                "assessment": assessment, "quality": self.window.diagnostics(),
                "timing": dict(self.timing), "counters": dict(self.counters),
                "configuration": self.config.metadata()}
