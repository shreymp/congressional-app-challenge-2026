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


def load_calibration(checkpoint_sha256):
    """Optional Platt calibration, bound to one checkpoint.

    Looks for CALIBRATION_PATH, else calibration.json beside the weights. Written by
    `model teseting/benchmark/calibrate.py` or the post-training notebook. A file for a
    different checkpoint stops startup instead of silently mis-scoring.
    CALIBRATION=off ignores any file.
    """
    if os.environ.get("CALIBRATION", "on") == "off":
        return None
    path = os.environ.get("CALIBRATION_PATH", os.path.join(WEIGHTS_DIR, "calibration.json"))
    if not os.path.exists(path):
        return None
    with open(path) as source:
        data = json.load(source)
    if data.get("schema") == "detector-calibration-v1":          # model teseting/benchmark/calibrate.py
        a, b, release = data["platt"]["a"], data["platt"]["b"], data.get("status") == "release"
    elif data.get("schema_version") == 1 and data.get("method") == "float64_call_weighted_platt":
        # model teseting/validation/calibrate.py fit: a candidate until frozen held-out validation passes.
        a, b, release = data["a"], data["b"], False
    else:
        raise ValueError("Unknown calibration schema")
    if not checkpoint_sha256 or data.get("checkpoint_sha256") != checkpoint_sha256:
        raise ValueError("calibration.json was fitted for a different checkpoint")
    if not release and os.environ.get("ALLOW_DEV_CALIBRATION") != "1":
        raise ValueError("calibration.json is not a release artifact; set ALLOW_DEV_CALIBRATION=1 to use it")
    return {"a": float(a), "b": float(b), "path": path, "status": data.get("status")}


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
        t_start = time.perf_counter()
        self.device = pick_device()
        self._det = Detector(WEIGHTS_DIR, device=self.device)
        self.meta = self._det.meta
        # Warm-up: the first call on MPS compiles kernels and is much slower than later ones.
        warmup = self._det.score(np.zeros(int(self.meta["window_sec"] * self.meta["sample_rate"]), np.float32),
                                 self.meta["sample_rate"])
        if not np.isfinite(warmup["mean"]):
            raise ValueError("Detector warmup returned nonfinite evidence")
        self.calibration = load_calibration(self._det.integrity["sha256"]["checkpoint"])
        self.diagnostics = {"ready": True, "device": self.device, "warmup_sec": round(time.perf_counter() - t_start, 3),
                            "integrity": self._det.integrity, "calibration": self.calibration}

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


class RemoteDetector:
    """Cloud jobs share the real model service instead of duplicating large weights."""
    mode = "real"

    def __init__(self):
        import urllib.request
        self.url = os.environ["DETECTOR_SERVICE_URL"].rstrip("/")
        if self.url != "http://127.0.0.1:8000":
            raise ValueError("Cloud detector service must be loopback")
        with urllib.request.urlopen(self.url + "/health", timeout=30) as response:
            health = json.load(response)
        if not health.get("deepfakeLoaded") or health.get("mode") != "real":
            raise RuntimeError("Real detector service is not ready")
        self.meta = health["meta"]
        self.device = health["device"]
        integrity = health.get("integrity") or {}
        self.calibration = load_calibration(integrity.get("sha256", {}).get("checkpoint"))
        self.diagnostics = {"ready": True, "device": self.device, "remote_health": True,
                            "integrity": health.get("integrity"), "integrity_verified": bool(health.get("integrity")),
                            "calibration": self.calibration}

    def score_window(self, audio):
        import urllib.request
        request = urllib.request.Request(self.url + "/deepfake",
            data=np.asarray(audio, dtype="<f4").tobytes(),
            headers={"Content-Type": "application/octet-stream"})
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)


def load():
    mode = os.environ.get("DETECTOR", "real").strip().lower()
    if mode == "stub":
        return StubDetector()
    if mode == "remote":
        return RemoteDetector()
    if mode == "real":
        return RealDetector()
    # Fail loudly: silently falling back to local weights hid a mangled cloud secret.
    raise ValueError(f"Unknown DETECTOR value {mode[:40]!r}; use real, remote or stub")


def thresholds(det) -> tuple[float, float]:
    """(elevated, high) as probabilities.

    Prefers logit-space thresholds (`logit_threshold_eer`, `logit_threshold_1pct_fpr` in
    detector_config.json, or THRESHOLD_ELEVATED_LOGIT / THRESHOLD_HIGH_LOGIT), converted in
    float64. The original probability thresholds were computed on saturated float32
    sigmoids: 0.9999998807907104 is 1 - 2*2^-24, so the true 1%-FPR logit is unknown.
    The engines clamp logits at about +/-27.6 (eps 1e-12), so keep logit thresholds below that.
    """
    meta = det.meta
    low_z = os.environ.get("THRESHOLD_ELEVATED_LOGIT", meta.get("logit_threshold_eer"))
    high_z = os.environ.get("THRESHOLD_HIGH_LOGIT", meta.get("logit_threshold_1pct_fpr"))
    if low_z is not None and high_z is not None:
        low_z, high_z = float(low_z), float(high_z)
        if not (low_z <= high_z < 27.6):
            raise ValueError("Logit thresholds must satisfy elevated <= high < 27.6")
        return _sigmoid(low_z), _sigmoid(high_z)
    elevated = float(os.environ.get("THRESHOLD_ELEVATED", meta["threshold_eer"]))
    high = float(os.environ.get("THRESHOLD_HIGH", meta["threshold_1pct_fpr"]))
    return elevated, high


if __name__ == "__main__":
    d = load()
    print(json.dumps({"device": d.device, "thresholds": thresholds(d)}))

