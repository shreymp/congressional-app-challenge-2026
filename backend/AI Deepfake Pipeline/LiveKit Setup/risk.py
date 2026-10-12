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

    def update(self, p_fake: float, z: float | None = None) -> dict:
        """p_fake: probability. z: the model's raw logit, if available (more precise near 1.0)."""
        if z is None:
            z = logit(p_fake)
        self.ema_logit = z if self.ema_logit is None else self.alpha * z + (1 - self.alpha) * self.ema_logit
        self.n_updates += 1

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
        }


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
