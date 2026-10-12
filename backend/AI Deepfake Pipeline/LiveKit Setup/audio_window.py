"""Rolling buffer of the caller's *voiced* audio at 16 kHz.

Frames arrive from LiveKit as int16 PCM (~10-20 ms each). Silent frames are dropped by a
simple energy gate so the detector isn't asked to judge silence or line hiss.

The energy gate is deliberately crude. If it misbehaves on real calls (cuts quiet talkers,
passes loud background noise), swap it for a proper VAD such as Silero.
"""
from __future__ import annotations

import numpy as np


class VoicedWindow:
    def __init__(self, sample_rate: int = 16000, window_sec: float = 4.0,
                 min_voiced_sec: float = 3.0, rms_threshold: float = 0.01):
        self.sr = sample_rate
        self.capacity = int(window_sec * sample_rate)
        self.min_samples = int(min_voiced_sec * sample_rate)
        self.rms_threshold = rms_threshold
        self.buf = np.zeros(self.capacity, dtype=np.float32)
        self.filled = 0                 # how many valid samples are in buf (<= capacity)
        self.total_voiced = 0           # samples of speech seen this call
        self.total_seen = 0             # all samples seen this call

    def push_int16(self, pcm: bytes | memoryview) -> bool:
        """Add one frame. Returns True if it counted as speech."""
        x = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        self.total_seen += len(x)
        if len(x) == 0 or float(np.sqrt(np.mean(x * x))) < self.rms_threshold:
            return False
        n = len(x)
        if n >= self.capacity:
            self.buf[:] = x[-self.capacity:]
        else:
            self.buf = np.roll(self.buf, -n)
            self.buf[-n:] = x
        self.filled = min(self.capacity, self.filled + n)
        self.total_voiced += n
        return True

    def ready(self) -> bool:
        return self.filled >= self.min_samples

    def snapshot(self) -> np.ndarray:
        """Copy of the most recent voiced audio (up to window_sec)."""
        return self.buf[-self.filled:].copy()
