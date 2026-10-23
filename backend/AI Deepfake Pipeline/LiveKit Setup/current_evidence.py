"""Development candidate: finite-horizon evidence with independent historical events.

All times are stream-relative seconds. Scores are bounded heuristics, not calibrated
probabilities. No threshold/checkpoint change is made by this experiment.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math

from risk import CallEvidenceEngine, logit, sigmoid


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    bounded: float
    weight: float


class CurrentEvidenceEngine:
    METHOD = "call-evidence-v2"

    def __init__(self, elevated_threshold, high_threshold, horizon_sec=16.0,
                 mode="mean", entry_steps=2, recovery_steps=2, min_segments=2,
                 min_usable_sec=3.0, entry_usable_sec=None, recovery_usable_sec=None,
                 warning_usable_sec=6.0, half_life_sec=8.0, calibration=None):
        base = CallEvidenceEngine(elevated_threshold, high_threshold, calibration=calibration)
        self.center, self.scale = base.center, base.scale
        self.horizon = float(horizon_sec)
        self.mode = mode
        self.min_segments = min_segments
        self.min_usable_sec = float(min_usable_sec)
        # Backward-compatible experiment API; operational rules are seconds of new speech.
        self.entry_sec = float(entry_usable_sec if entry_usable_sec is not None else entry_steps * 1.5)
        self.recovery_sec = float(recovery_usable_sec if recovery_usable_sec is not None else recovery_steps * 1.5)
        self.warning_sec = float(warning_usable_sec)
        self.half_life = float(half_life_sec)
        if (mode not in ("mean", "decay") or min_segments < 1
                or any(not math.isfinite(v) or v <= 0 for v in
                       (self.horizon, self.min_usable_sec, self.entry_sec, self.recovery_sec,
                        self.warning_sec, self.half_life))):
            raise ValueError("Invalid current-evidence configuration")
        self.segments = deque()
        self.events = deque(maxlen=64)
        self._warning_open = False
        self._next_event = 1
        self.last_end = None
        self.last_start = None
        self.last = None

    def _trim(self, now):
        cutoff = now - self.horizon
        while self.segments and self.segments[0].end <= cutoff:
            self.segments.popleft()

    def update(self, p_fake, z=None, weight=1.0, *, start_sec, end_sec):
        """Add one completed model result.

        For overlapping windows, `weight` MUST be the estimated speech fraction in
        the genuinely new tail [max(start_sec,last_end),end_sec], measured by caller.
        A full-window speech fraction would count old speech again. Live scoring
        deliberately uses distinct windows, so its full-window fraction is valid.
        """
        vals = (p_fake, weight, start_sec, end_sec)
        if (any(not math.isfinite(v) for v in vals) or not 0 <= p_fake <= 1
                or not 0 < weight <= 1 or start_sec < 0 or end_sec <= start_sec
                or (z is not None and not math.isfinite(z))):
            raise ValueError("Invalid timestamped evidence")
        if self.last_end is not None and end_sec <= self.last_end:
            raise ValueError("Evidence must add new audio")
        # Only genuinely new audio contributes, even if experiments use overlapping inputs.
        if self.last_end is not None and end_sec - self.last_end >= self.horizon:
            self._warning_open = False
            if self.events:
                self.events[-1]["current"] = False
        start = max(start_sec, self.last_end if self.last_end is not None else start_sec)
        z = logit(p_fake) if z is None else z
        bounded = max(-4.0, min(4.0, (z - self.center) / self.scale))
        self.segments.append(Segment(start, end_sec, bounded, weight))
        self.last_start, self.last_end = start_sec, end_sec
        self._trim(end_sec)
        out = self._evaluate(end_sec)
        if out["recent_ai"]:
            if not self._warning_open:
                warning_start = min(seg.start for seg in self.segments if 100 * sigmoid(seg.bounded) >= 65)
                self.events.append({"id": str(self._next_event), "start_sec": warning_start,
                                    "end_sec": end_sec, "current": True})
                self._next_event += 1
            else:
                self.events[-1]["end_sec"] = end_sec
        elif self._warning_open:
            self.events[-1]["current"] = False
        self._warning_open = out["recent_ai"]
        self.last = out
        return out

    @staticmethod
    def _target(score):
        return "human" if score <= 35 else "ai" if score >= 65 else "uncertain"

    def _evaluate(self, now):
        self._trim(now)
        segments = list(self.segments)
        cutoff = now - self.horizon
        # Replay only retained evidence: hysteresis cannot preserve an old state indefinitely.
        state, pending, pending_speech = "analyzing", None, 0.0
        weighted = weight = usable = ai_usable = 0.0
        score = None
        seen = 0
        for i, seg in enumerate(segments):
            duration = max(0.0, seg.end - max(seg.start, cutoff)) * seg.weight
            if not duration:
                continue
            seen += 1
            # Decay is measured in new usable speech, and remains bounded by the horizon.
            if self.mode == "decay":
                decay = 2 ** (-duration / self.half_life)
                weighted *= decay
                weight *= decay
            weighted += seg.bounded * duration
            weight += duration
            usable += duration
            if 100 * sigmoid(seg.bounded) >= 65:
                ai_usable += duration
            score = 100 * sigmoid(weighted / weight)
            target = self._target(score)
            if seen < self.min_segments or usable < self.min_usable_sec:
                continue
            if state == "analyzing":
                state = target
            elif target != state:
                pending_speech = pending_speech + duration if pending == target else duration
                pending = target
                required = self.entry_sec if target == "ai" else self.recovery_sec
                if pending_speech >= required:
                    state, pending, pending_speech = target, None, 0.0
            else:
                pending, pending_speech = None, 0.0
        recent_ai = bool(seen >= self.min_segments and ai_usable >= self.warning_sec
                         and score is not None and score >= 65)
        age = None if self.last_end is None else max(0.0, now - self.last_end)
        freshness = "none" if self.last_end is None else "stale" if not segments else "fresh"
        return {"method": self.METHOD, "state": state, "score": None if score is None else round(score, 1),
                "score_kind": "heuristic", "recent_ai": recent_ai, "pending_state": pending,
                "evidence_start_sec": self.last_start if not segments else max(cutoff, segments[0].start),
                "evidence_end_sec": self.last_end, "evidence_age_sec": age,
                "freshness": freshness, "usable_sec": round(usable, 3), "updates": seen,
                "level": "high" if state == "ai" else "elevated" if state == "uncertain" else "listening"}

    def snapshot(self, now):
        if not math.isfinite(now) or now < 0:
            raise ValueError("Invalid current-evidence clock")
        # A heartbeat may age a result to stale, but cannot change its classification
        # merely by trimming the older half of mixed evidence during silence.
        if self.last is not None and now - self.last_end < self.horizon:
            out = dict(self.last)
            out["evidence_age_sec"] = max(0.0, now - self.last_end)
        else:
            out = self._evaluate(now)
        current = out["recent_ai"] and out["freshness"] == "fresh"
        out["historical_warning_events"] = [dict(event, current=bool(current and i == len(self.events)-1
                                                                and self._warning_open))
                                            for i, event in enumerate(self.events)]
        return out
