"""Trained speech detector for the eligibility gate (Silero VAD via livekit-plugins-silero).

Why: the fixed RMS gate and the heuristic adaptive gate both let DTMF tones and tonal
music reach the deepfake model, which scores them around logit 48-52 (far above clean AI
speech). In development checks Silero marked 0% of silence, white/low-pass noise, DTMF,
a synthetic chord and a synthetic melody as speech, while keeping about 85-89% of frames
of the two LibriSpeech controls clean, at -20 dB, at 10/20 dB SNR and band-limited to 8 kHz.
Those are synthetic controls and two speakers, not real hold music, TV or crosstalk.

`livekit.plugins.silero.onnx_model` is an internal module of the plugin, not a documented
public API. It was checked against livekit-plugins-silero 1.8.8 (Oct 2026). Pin that version
and re-check `OnnxModel(onnx_session=..., sample_rate=...)` and `model(chunk) -> float`
before upgrading.
"""
from __future__ import annotations

import threading

import numpy as np

SPEECH_PROBABILITY = 0.5
_session = None
_lock = threading.Lock()


def _shared_session():
    global _session
    with _lock:
        if _session is None:
            from livekit.plugins.silero.onnx_model import new_inference_session
            _session = new_inference_session(True)
        return _session


def check_available() -> None:
    """Fail at worker startup, not inside a call, if the VAD cannot load."""
    SileroSpeechDetector(16000)


class SileroSpeechDetector:
    """Streaming per-call state over one shared ONNX session. Not thread-safe per instance."""

    def __init__(self, sample_rate: int):
        try:
            from livekit.plugins.silero.onnx_model import OnnxModel
        except ImportError as exc:  # pragma: no cover - depends on deployment image
            raise RuntimeError("SPEECH_GATE=silero needs livekit-plugins-silero installed") from exc
        self._model = OnnxModel(onnx_session=_shared_session(), sample_rate=sample_rate)
        self.chunk = int(self._model.window_size_samples)

    def __call__(self, chunk: np.ndarray) -> float:
        if len(chunk) != self.chunk:
            raise ValueError("VAD chunk has the wrong length")
        p = float(self._model(np.asarray(chunk, dtype=np.float32)[None, :]))
        if not np.isfinite(p):
            raise ValueError("VAD returned a nonfinite probability")
        return p

    def reset(self) -> None:
        self._model.reset()
