"""Silero speech gate and config wiring. Skips the VAD tests if the plugin is not installed."""
import importlib.util
from pathlib import Path
import unittest

import numpy as np

from audio_window import VoicedWindow
from pipeline_config import ScoringConfig

HAS_SILERO = importlib.util.find_spec("livekit.plugins.silero") is not None
SR = 16000
HUMAN = Path(__file__).resolve().parents[3] / "model teseting/audio/human_controls"


def feed(window, audio, chunk=320):
    pcm = np.clip(np.asarray(audio) * 32768, -32768, 32767).astype(np.int16)
    for i in range(0, len(pcm), chunk):
        window.push_int16(pcm[i:i + chunk].tobytes())


def controls():
    rng = np.random.default_rng(7)
    t = np.arange(SR * 8) / SR
    dtmf = (np.sin(2*np.pi*697*t) + np.sin(2*np.pi*1209*t)) * ((t % 1) < .5)
    chord = sum(np.sin(2*np.pi*f*t) for f in (220, 277.18, 329.63, 440)) * (.6 + .4*np.sin(2*np.pi*2*t))
    norm = lambda s, level: s / np.sqrt(np.mean(s ** 2)) * level
    return {"white_noise": norm(rng.standard_normal(len(t)), .03), "dtmf": norm(dtmf, .03),
            "chord": norm(chord, .03), "tone": .05 * np.sin(2*np.pi*440*t)}


class ConfigTests(unittest.TestCase):
    def test_gate_selection_and_validation(self):
        self.assertEqual(ScoringConfig().gate, "fixed")
        self.assertEqual(ScoringConfig(quiet_enabled=True).gate, "adaptive")
        self.assertEqual(ScoringConfig(speech_gate="silero").gate, "silero")
        self.assertEqual(ScoringConfig().metadata()["effective_gate"], "fixed")
        for bad in ({"speech_gate": "webrtc"}, {"quiet_enabled": True, "speech_gate": "silero"},
                    {"digital_silence_max_sec": 0}, {"digital_silence_max_sec": 5}):
            with self.assertRaises(ValueError):
                ScoringConfig(**bad)


@unittest.skipUnless(HAS_SILERO, "livekit-plugins-silero not installed")
class SileroGateTests(unittest.TestCase):
    def test_non_speech_controls_never_become_eligible(self):
        for name, audio in controls().items():
            window = VoicedWindow(gate_mode="silero")
            feed(window, audio)
            self.assertFalse(window.ready(), name)
            self.assertEqual(window.total_voiced, 0, name)
            self.assertEqual(window.rejection_reason, "insufficient_speech", name)
            # The DTMF control is on/off keyed with exact zeros, so the silence guard may fire first.
            self.assertIn(window.quality_detail, ("no_speech_detected", "digital_silence_gap"), name)

    def test_chunking_does_not_change_decisions(self):
        audio = controls()["chord"][:SR * 5] + np.random.default_rng(1).normal(0, .01, SR * 5)
        a, b = VoicedWindow(gate_mode="silero"), VoicedWindow(gate_mode="silero")
        feed(a, audio, 320)
        feed(b, audio, 137)
        np.testing.assert_array_equal(a.speech, b.speech)
        np.testing.assert_array_equal(a.snapshot(), b.snapshot())

    @unittest.skipUnless(HUMAN.exists(), "human control audio not present")
    def test_quiet_and_noisy_real_speech_stays_eligible(self):
        import soundfile as sf
        for path in sorted(HUMAN.glob("*.wav")):
            speech, sr = sf.read(path, dtype="float32")
            self.assertEqual(sr, SR)
            noise = np.random.default_rng(2).standard_normal(len(speech)) * np.sqrt(np.mean(speech ** 2)) / 10 ** .5
            for label, audio in (("clean", speech), ("-20 dB", speech * .1), ("10 dB SNR", speech + noise)):
                window = VoicedWindow(gate_mode="silero")
                feed(window, audio)
                self.assertGreater(window.total_voiced / window.total_seen, .7, (path.name, label))
                self.assertTrue(window.ready() or window.quality_detail == "digital_silence_gap", (path.name, label))

    def test_reset_clears_vad_state(self):
        window = VoicedWindow(gate_mode="silero")
        feed(window, controls()["white_noise"][:SR])
        window.reset_audio()
        self.assertEqual(window.filled, 0)
        self.assertFalse(window.digital.any())


if __name__ == "__main__":
    unittest.main()
