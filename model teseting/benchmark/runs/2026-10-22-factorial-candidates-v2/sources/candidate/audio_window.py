"""Contiguous caller audio, with fixed and development-only adaptive eligibility.

`total_voiced` and `weight` estimate speech from a gate; neither is a validated VAD.
Natural pauses are retained. No waveform gain is applied before eligibility.
"""
from __future__ import annotations

from collections import deque
import numpy as np


class VoicedWindow:
    def __init__(self, sample_rate=16000, window_sec=4.0,
                 min_voiced_sec=1.5, rms_threshold=.01, gate_mode="fixed"):
        self.sr = sample_rate
        self.capacity = int(window_sec * sample_rate)
        self.min_samples = int(min_voiced_sec * sample_rate)
        if self.sr <= 0 or self.capacity <= 0 or not 0 < self.min_samples <= self.capacity:
            raise ValueError("Invalid audio window configuration")
        if gate_mode not in ("fixed", "adaptive"):
            raise ValueError("Unknown gate mode")
        self.gate_mode, self.rms_threshold = gate_mode, rms_threshold
        self.buf = np.zeros(self.capacity, dtype=np.float32)
        self.speech = np.zeros(self.capacity, dtype=np.bool_)
        self.clipped = np.zeros(self.capacity, dtype=np.bool_)
        self.filled = self.total_voiced = self.total_seen = 0
        self.energy = deque(maxlen=250)
        self.frame_rms = self.noise_floor = self.flatness = self.band_ratio = 0.0
        self.speech_decision = False
        self.rejections = {key: 0 for key in ("insufficient_speech", "audio_too_quiet",
                                             "audio_too_noisy", "audio_distorted")}
        self._partial = np.empty(0, dtype=np.float32)

    def _adaptive(self, x):
        rms = float(np.sqrt(np.mean(x * x)))
        self.frame_rms = rms
        prior = list(self.energy)
        self.noise_floor = float(np.percentile(prior, 15)) if len(prior) >= 25 else .0001
        self.energy.append(rms)
        centered = x - x.mean()
        spectrum = np.abs(np.fft.rfft(centered * np.hanning(len(x)))) ** 2
        power = spectrum + 1e-18
        self.flatness = float(np.exp(np.mean(np.log(power))) / np.mean(power))
        freq = np.fft.rfftfreq(len(x), 1 / self.sr)
        self.band_ratio = float(power[(freq >= 100) & (freq <= 3800)].sum() / power.sum())
        crest = float(np.max(np.abs(centered)) / (np.sqrt(np.mean(centered * centered)) + 1e-12))
        # Spectral tests reject steady broadband hiss and pure tones, even during startup.
        # Percentile floor is an estimate; this is explicitly not a trained speech detector.
        threshold = max(.00035, self.noise_floor * 1.7)
        return bool(rms >= threshold and self.flatness < .45 and self.band_ratio > .45
                    and crest > 1.8)

    def _append(self, x, voiced):
        n = len(x)
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
        self.speech_decision = voiced

    def push_int16(self, pcm):
        if len(pcm) % 2:
            raise ValueError("Incomplete int16 sample")
        x = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        if not len(x):
            return False
        if self.gate_mode == "fixed":
            self.frame_rms = float(np.sqrt(np.mean(x * x)))
            voiced = self.frame_rms >= self.rms_threshold
            self._append(x, voiced)
            return voiced
        # Eligibility features always use complete 20 ms frames; transport chunking is irrelevant.
        x = np.concatenate((self._partial, x))
        size = max(1, round(self.sr * .02))
        complete = len(x) // size * size
        any_speech = False
        for start in range(0, complete, size):
            frame = x[start:start + size]
            voiced = self._adaptive(frame)
            self._append(frame, voiced)
            any_speech |= voiced
        self._partial = x[complete:].copy()
        return any_speech

    @property
    def rejection_reason(self):
        if float(self.clipped.mean()) > .05:
            return "audio_distorted"
        if self.filled < self.capacity:
            return "insufficient_speech"
        if np.count_nonzero(self.speech) >= self.min_samples:
            return None
        rms = float(np.sqrt(np.mean(self.buf * self.buf)))
        if rms < (.00035 if self.gate_mode == "adaptive" else self.rms_threshold):
            return "audio_too_quiet" if rms > 0 else "insufficient_speech"
        return "audio_too_noisy" if self.gate_mode == "adaptive" else "insufficient_speech"

    def ready(self):
        return self.rejection_reason is None

    @property
    def weight(self):
        return float(self.speech.mean())

    def diagnostics(self):
        return {"gate": self.gate_mode, "frame_rms": round(self.frame_rms, 7),
                "noise_floor_estimate": round(self.noise_floor, 7),
                "spectral_flatness": round(self.flatness, 5), "speech_decision": self.speech_decision,
                "eligible_speech_sec_estimate": round(np.count_nonzero(self.speech) / self.sr, 3),
                "clipping_fraction": round(float(self.clipped.mean()), 5),
                "rejection_reason": self.rejection_reason}

    def reset_audio(self):
        self.filled = 0
        self.buf.fill(0)
        self.speech.fill(False)
        self.clipped.fill(False)
        self._partial = np.empty(0, dtype=np.float32)

    def snapshot(self):
        return self.buf.copy()
