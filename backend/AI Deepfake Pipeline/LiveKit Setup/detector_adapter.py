"""The one plug between the call agent and the deepfake model.

The agent only ever calls `load()` once per process and `score_window(audio16k)` per update.
To move the model somewhere else later (a GPU service, an ONNX export), change this file
only. Set DETECTOR=stub to run the whole call path without loading the 650 MB model.
"""
from __future__ import annotations

import json
import os
import random
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
# inference.py, detector_config.json and best.pt live one folder up, in "AI Deepfake Pipeline".
WEIGHTS_DIR = os.environ.get("DETECTOR_WEIGHTS_DIR", os.path.abspath(os.path.join(HERE, "..")))


def _sigmoid(z: float) -> float:
    import math
    return 1 / (1 + math.exp(-z)) if z >= 0 else math.exp(z) / (1 + math.exp(z))


def pick_device() -> str:
    forced = os.environ.get("DETECTOR_DEVICE")
    if forced:
        return forced
    import torch
    if torch.backends.mps.is_available():   # Apple Silicon GPU (the M5 Pro MacBook)
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


class StubDetector:
    """Fake scores so the LiveKit plumbing can be tested before the real model is wired in."""
    meta = {"threshold_eer": 0.9999904632568359, "threshold_1pct_fpr": 0.9999998807907104,
            "sample_rate": 16000, "window_sec": 4.0}
    device = "stub"
    mode = "stub"

    def score_window(self, audio: np.ndarray) -> dict:
        time.sleep(0.02)
        z = random.uniform(-6.0, 0.0)
        return {"p_fake": _sigmoid(z), "logit": z, "infer_ms": 20.0}


class RealDetector:
    mode = "real"
    def __init__(self):
        if WEIGHTS_DIR not in sys.path:
            sys.path.insert(0, WEIGHTS_DIR)
        from inference import Detector          # the team's existing inference.py
        self.device = pick_device()
        self._det = Detector(WEIGHTS_DIR, device=self.device)
        self.meta = self._det.meta
        # Warm-up: the first call on MPS compiles kernels and is much slower than later ones.
        self._det.score(np.zeros(int(self.meta["window_sec"] * self.meta["sample_rate"]), np.float32),
                        self.meta["sample_rate"])

    def score_window(self, audio: np.ndarray) -> dict:
        """Score the most recent window. Same preprocessing as inference.py's Detector.score,
        but returns the raw logit too: in float32 the sigmoid rounds everything above
        ~0.99999994 to exactly 1.0, which is right where the config thresholds sit."""
        import torch
        t0 = time.perf_counter()
        win = int(self.meta["window_sec"] * self.meta["sample_rate"])
        x = np.asarray(audio, dtype=np.float32)
        if x.ndim != 1 or len(x) == 0 or not np.isfinite(x).all():
            raise ValueError("Expected nonempty, finite mono audio")
        if len(x) < win:
            x = np.tile(x, int(np.ceil(win / max(len(x), 1))))[:win]
        x = x[-win:]
        x = (x - x.mean()) / (x.std() + 1e-7)
        with torch.no_grad():
            z = float(self._det.model(torch.from_numpy(x)[None].to(self.device)).item())
        return {"p_fake": _sigmoid(z), "logit": z, "infer_ms": (time.perf_counter() - t0) * 1000}


def load():
    if os.environ.get("DETECTOR", "real").lower() == "stub":
        return StubDetector()
    return RealDetector()


def thresholds(det) -> tuple[float, float]:
    """(elevated, high). Env vars override the config so they can be recalibrated on phone audio."""
    elevated = float(os.environ.get("THRESHOLD_ELEVATED", det.meta["threshold_eer"]))
    high = float(os.environ.get("THRESHOLD_HIGH", det.meta["threshold_1pct_fpr"]))
    return elevated, high


if __name__ == "__main__":
    d = load()
    print(json.dumps({"device": d.device, "thresholds": thresholds(d)}))
