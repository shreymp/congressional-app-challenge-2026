"""Contiguous caller audio; speech gates eligibility without deleting natural pauses."""
from __future__ import annotations

import numpy as np


class VoicedWindow:
    def __init__(self, sample_rate=16000, window_sec=4.0,
                 min_voiced_sec=1.5, rms_threshold=.01):
        self.sr = sample_rate
        self.capacity = int(window_sec * sample_rate)
        self.min_samples = int(min_voiced_sec * sample_rate)
        self.rms_threshold = rms_threshold
        self.buf = np.zeros(self.capacity, dtype=np.float32)
        self.speech = np.zeros(self.capacity, dtype=np.bool_)
        self.clipped = np.zeros(self.capacity, dtype=np.bool_)
        self.filled = self.total_voiced = self.total_seen = 0

    def push_int16(self, pcm):
        x = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        n = len(x)
        if not n:
            return False
        voiced = float(np.sqrt(np.mean(x * x))) >= self.rms_threshold
        self.total_seen += n
        if voiced:
            self.total_voiced += n
        take = min(n, self.capacity)
        for buf in (self.buf, self.speech, self.clipped):
            buf[:-take] = buf[take:]
        self.buf[-take:] = x[-take:]
        self.speech[-take:] = voiced
        self.clipped[-take:] = np.abs(x[-take:]) >= .99
        self.filled = min(self.capacity, self.filled + n)
        return voiced

    def ready(self):
        return (self.filled == self.capacity and np.count_nonzero(self.speech) >= self.min_samples
                and float(self.clipped.mean()) <= .05)

    @property
    def weight(self):
        return float(self.speech.mean())

    def snapshot(self):
        return self.buf.copy()
