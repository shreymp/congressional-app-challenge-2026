"""Risk engine: turns a noisy stream of per-window deepfake scores into a stable level.

Pure Python, no LiveKit imports, so it can be unit-tested offline.

Why logit space: the detector's scores are extremely saturated (its 1%-FPR threshold
in detector_config.json is 0.99999988). Averaging raw probabilities that close to 1
hides all the differences, so we smooth log-odds instead.

Levels:
  listening  - not enough speech yet, or scores below the "elevated" threshold
  elevated   - smoothed score stayed above the EER threshold for `up_steps` updates
  high       - smoothed score stayed above the 1%-FPR threshold for `up_steps` updates
Levels only drop after `down_steps` consecutive updates below the threshold (hysteresis),
so one quiet window can't flip a warning off and back on.

"Prevention mode" is deliberately NOT decided here yet: per the design, it should need
the transcript signal as well, not the voice signal alone. See combine() below.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field

LEVELS = ("listening", "elevated", "high")


def logit(p: float, eps: float = 1e-12) -> float:
    p = min(max(p, eps), 1 - eps)
    return math.log(p / (1 - p))


def sigmoid(x: float) -> float:
    if x >= 0:
        return 1 / (1 + math.exp(-x))
    e = math.exp(x)
    return e / (1 + e)


@dataclass
class RiskEngine:
    elevated_threshold: float          # probability, e.g. detector_config threshold_eer
    high_threshold: float              # probability, e.g. detector_config threshold_1pct_fpr
    alpha: float = 0.4                 # EMA weight on the newest window
    up_steps: int = 3                  # consecutive updates above a threshold to escalate
    down_steps: int = 5                # consecutive updates below to de-escalate
    level: str = "listening"
    ema_logit: float | None = None
    n_updates: int = 0
    _above: dict = field(default_factory=lambda: {"elevated": 0, "high": 0})
    _below: int = 0
    _human_steps: int = 0

    def __post_init__(self):
        if not (0 < self.elevated_threshold <= self.high_threshold < 1):
            raise ValueError("Thresholds must satisfy 0 < elevated <= high < 1")
        if not (0 < self.alpha <= 1 and self.up_steps > 0 and self.down_steps > 0):
            raise ValueError("Invalid smoothing parameters")

    def update(self, p_fake: float, z: float | None = None) -> dict:
        """p_fake: probability. z: the model's raw logit, if available (more precise near 1.0)."""
        if not math.isfinite(p_fake) or not 0 <= p_fake <= 1 or (z is not None and not math.isfinite(z)):
            raise ValueError("Non-finite or out-of-range detector score")
        if z is None:
            z = logit(p_fake)
        self.ema_logit = z if self.ema_logit is None else self.alpha * z + (1 - self.alpha) * self.ema_logit
        self.n_updates += 1
        self._human_steps = self._human_steps + 1 if self.ema_logit < logit(self.elevated_threshold) else 0

        target = "listening"
        for name, thr in (("elevated", self.elevated_threshold), ("high", self.high_threshold)):
            if self.ema_logit >= logit(thr):
                self._above[name] += 1
                if self._above[name] >= self.up_steps:
                    target = name
            else:
                self._above[name] = 0

        cur, tgt = LEVELS.index(self.level), LEVELS.index(target)
        if tgt > cur:                       # escalate immediately once sustained
            self.level, self._below = target, 0
        elif tgt < cur:                     # de-escalate only after a sustained drop
            self._below += 1
            if self._below >= self.down_steps:
                self.level, self._below = target, 0
        else:
            self._below = 0

        return {
            "p_last": p_fake,
            "logit_last": round(z, 3),
            "p_smoothed": sigmoid(self.ema_logit),
            "logit_smoothed": round(self.ema_logit, 3),
            "level": self.level,
            "updates": self.n_updates,
            "human_steps": self._human_steps,
        }


class CallEvidenceEngine:
    """Bounded, speech-weighted call evidence. AI score is NOT a probability.

    RiskEngine remains above for legacy wire replays. Threshold-relative logits
    retain precision for saturated model outputs. This mapping is a documented
    heuristic until representative phone-call calibration data is available.
    """
    METHOD = "call-evidence-v1"
    MIN_SEGMENTS = 2
    HUMAN_SCORE = 35.0
    AI_SCORE = 65.0

    def __init__(self, elevated_threshold, high_threshold):
        RiskEngine(elevated_threshold, high_threshold)
        low, high = logit(elevated_threshold), logit(high_threshold)
        self.center = (low + high) / 2
        self.scale = max((high - low) / (2 * logit(.65)), .25)
        self.weighted = self.weight = 0.0
        self.n_updates = self.human_steps = 0
        self.state = "analyzing"
        self.candidate = None
        self.candidate_steps = 0
        self.recent = deque(maxlen=5)
        self.ai_run = self.max_ai_run = 0

    def update(self, p_fake, z=None, weight=1.0):
        if (not math.isfinite(p_fake) or not 0 <= p_fake <= 1
                or (z is not None and not math.isfinite(z))
                or not math.isfinite(weight) or not 0 < weight <= 1):
            raise ValueError("Invalid caller evidence")
        z = logit(p_fake) if z is None else z
        bounded = max(-4.0, min(4.0, (z - self.center) / self.scale))
        self.weighted += weight * bounded
        self.weight += weight
        self.n_updates += 1
        self.recent.append((bounded, weight))
        mean = self.weighted / self.weight
        score = 100 * sigmoid(mean)
        segment_score = 100 * sigmoid(bounded)
        self.human_steps = self.human_steps + 1 if segment_score <= self.HUMAN_SCORE else 0
        self.ai_run = self.ai_run + 1 if segment_score >= self.AI_SCORE else 0
        self.max_ai_run = max(self.max_ai_run, self.ai_run)
        target = "human" if score <= self.HUMAN_SCORE else "ai" if score >= self.AI_SCORE else "uncertain"
        if self.n_updates >= self.MIN_SEGMENTS:
            if self.state == "analyzing":
                self.state = target
            elif target != self.state:
                self.candidate_steps = self.candidate_steps + 1 if self.candidate == target else 1
                self.candidate = target
                if self.candidate_steps >= 2:
                    self.state = target
                    self.candidate_steps = 0
            else:
                self.candidate = None
                self.candidate_steps = 0
        recent_mean = sum(z * w for z, w in self.recent) / sum(w for _, w in self.recent)
        recent_ai = (len(self.recent) >= 3 and 100 * sigmoid(recent_mean) >= self.AI_SCORE
                     and sum(100 * sigmoid(z) >= self.AI_SCORE for z, _ in self.recent) >= 3)
        aggregate_logit = self.center + self.scale * mean
        return {"method": self.METHOD, "state": self.state, "score": round(score, 1),
                "score_kind": "heuristic", "recent_ai": recent_ai, "max_ai_run": self.max_ai_run,
                "level": "high" if self.state == "ai" else "elevated" if self.state == "uncertain" else "listening",
                "updates": self.n_updates, "human_steps": self.human_steps,
                "p_last": p_fake, "logit_last": round(z, 3),
                "p_smoothed": sigmoid(aggregate_logit), "logit_smoothed": round(aggregate_logit, 3)}


def combine(deepfake_level: str, transcript_probability: float | None) -> str:
    """Placeholder fusion rule. Returns the overall call level.

    TODO(team): replace once the transcript branch is live and calibrated. Current rule:
    voice alone can reach 'high' but never 'prevention'; prevention needs both signals.
    """
    if transcript_probability is None:
        return deepfake_level
    if deepfake_level == "high" and transcript_probability >= 0.8:
        return "prevention"
    if transcript_probability >= 0.8 and deepfake_level == "listening":
        return "elevated"
    return deepfake_level
