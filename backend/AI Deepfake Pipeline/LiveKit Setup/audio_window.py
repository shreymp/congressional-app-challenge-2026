"""Contiguous caller audio, with fixed, heuristic-adaptive or Silero VAD eligibility.

`total_voiced` and `weight` estimate speech from a gate. Only the `silero` gate uses a
trained speech detector; `fixed` and `adaptive` are energy/spectral heuristics.
Natural pauses are retained. No waveform gain is applied before eligibility.

Digital-silence guard (all gates): a window containing a run of exact digital silence
(|sample| <= 2 LSB) longer than `digital_silence_max_sec` is not submitted. In the
2026-10-22 benchmark, windows holding 2 s of inserted digital silence plus 2 s of real
human speech scored logits 31.3 and 33.8, above every clean AI window median (about 25-27).
Real phone audio between words normally carries a noise floor; exact zeros can come from
muting, silence suppression or packet-loss concealment. Pass `digital_silence_max_sec=None`
to disable. The root cause is in the model and needs post-training.
"""
from __future__ import annotations

from collections import deque
import numpy as np


class VoicedWindow:
    def __init__(self, sample_rate=16000, window_sec=4.0,
                 min_voiced_sec=1.5, rms_threshold=.01, gate_mode="fixed",
                 digital_silence_max_sec=.2):
        self.sr = sample_rate
        self.capacity = int(window_sec * sample_rate)
        self.min_samples = int(min_voiced_sec * sample_rate)
        if self.sr <= 0 or self.capacity <= 0 or not 0 < self.min_samples <= self.capacity:
            raise ValueError("Invalid audio window configuration")
        if gate_mode not in ("fixed", "adaptive", "silero"):
            raise ValueError("Unknown gate mode")
        if digital_silence_max_sec is not None and not 0 < digital_silence_max_sec < window_sec:
            raise ValueError("Invalid digital silence limit")
        self.digital_max = (None if digital_silence_max_sec is None
                            else int(digital_silence_max_sec * sample_rate))
        self.gate_mode, self.rms_threshold = gate_mode, rms_threshold
        self.buf = np.zeros(self.capacity, dtype=np.float32)
        self.speech = np.zeros(self.capacity, dtype=np.bool_)
        self.clipped = np.zeros(self.capacity, dtype=np.bool_)
        self.digital = np.zeros(self.capacity, dtype=np.bool_)
        self._run_cache = (-1, 0)
        self.vad_probability = None
        self._vad = None
        if gate_mode == "silero":
            from speech_vad import SileroSpeechDetector
            self._vad = SileroSpeechDetector(sample_rate)
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
        for buf in (self.buf, self.speech, self.clipped, self.digital):
            buf[:-take] = buf[take:]
        self.buf[-take:] = x[-take:]
        self.speech[-take:] = voiced
        self.clipped[-take:] = np.abs(x[-take:]) >= .99
        self.digital[-take:] = np.abs(x[-take:]) <= 2.5 / 32768
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
        # Eligibility features always use complete frames; transport chunking is irrelevant.
        x = np.concatenate((self._partial, x))
        if self.gate_mode == "silero":
            size, complete, any_speech = self._vad.chunk, len(x) // self._vad.chunk * self._vad.chunk, False
            for start in range(0, complete, size):
                frame = x[start:start + size]
                self.frame_rms = float(np.sqrt(np.mean(frame * frame)))
                self.vad_probability = self._vad(frame)
                voiced = self.vad_probability >= .5
                self._append(frame, voiced)
                any_speech |= voiced
            self._partial = x[complete:].copy()
            return any_speech
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
    def longest_digital_silence(self):
        """Longest run, in samples, of exact digital silence inside the filled window."""
        if self._run_cache[0] != self.total_seen:
            mask = self.digital[self.capacity - self.filled:] if self.filled else self.digital[:0]
            longest = 0
            if mask.any():
                edges = np.flatnonzero(np.diff(np.concatenate(([0], mask.view(np.int8), [0]))))
                longest = int((edges[1::2] - edges[::2]).max())
            self._run_cache = (self.total_seen, longest)
        return self._run_cache[1]

    @property
    def quality_detail(self):
        """Finer reason for diagnostics. The wire `rejection_reason` keeps the v2 vocabulary."""
        if float(self.clipped.mean()) > .05:
            return "audio_distorted"
        if self.filled < self.capacity:
            return "window_filling"
        if self.digital_max is not None and self.longest_digital_silence > self.digital_max:
            return "digital_silence_gap"
        if np.count_nonzero(self.speech) >= self.min_samples:
            return None
        rms = float(np.sqrt(np.mean(self.buf * self.buf)))
        if rms < (self.rms_threshold if self.gate_mode == "fixed" else .00035):
            return "audio_too_quiet" if rms > 0 else "no_signal"
        return "no_speech_detected" if self.gate_mode == "silero" else (
            "audio_too_noisy" if self.gate_mode == "adaptive" else "insufficient_speech")

    @property
    def rejection_reason(self):
        detail = self.quality_detail
        if detail in (None, "audio_distorted", "audio_too_quiet", "audio_too_noisy", "insufficient_speech"):
            return detail
        # window_filling, digital_silence_gap, no_signal and no_speech_detected map to the
        # existing wire value so older and current iPhone decoders still accept the packet.
        return "insufficient_speech"

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
                "digital_silence_max_run_sec": round(self.longest_digital_silence / self.sr, 3),
                "vad_probability": None if self.vad_probability is None else round(self.vad_probability, 4),
                "quality_detail": self.quality_detail,
                "rejection_reason": self.rejection_reason}

    def reset_audio(self):
        self.filled = 0
        self.buf.fill(0)
        self.speech.fill(False)
        self.clipped.fill(False)
        self.digital.fill(False)
        self._run_cache = (-1, 0)
        if self._vad is not None:
            self._vad.reset()
        self._partial = np.empty(0, dtype=np.float32)

    def snapshot(self):
        return self.buf.copy()
