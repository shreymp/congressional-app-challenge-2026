"""Invariant tests; synthetic evidence checks are not accuracy/held-out validation."""
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from audio_window import VoicedWindow
from current_evidence import CurrentEvidenceEngine
from pipeline_config import ScoringConfig
from risk import sigmoid
from scoring import AudioScoringSession
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from model_integrity import sha256, verify_bundle

THRESHOLDS = (.9999904632568359, .9999998807907104)


class CurrentTests(unittest.TestCase):
    def add(self, engine, z, end):
        return engine.update(sigmoid(z), z, start_sec=end-4, end_sec=end)

    def test_history_outside_horizon_has_no_influence_in_either_direction(self):
        for mode in ("mean", "decay"):
            for before, after in ((-2, 30), (30, -2)):
                short = CurrentEvidenceEngine(*THRESHOLDS, mode=mode)
                long = CurrentEvidenceEngine(*THRESHOLDS, mode=mode)
                for end in range(4, 121, 4):
                    self.add(long, before, end)
                for end in range(124, 145, 4):
                    a, b = self.add(short, after, end), self.add(long, after, end)
                self.assertEqual(a["state"], b["state"])
                self.assertEqual(a["score"], b["score"])
                self.assertEqual(a["state"], "ai" if after == 30 else "human")

    def test_silence_expires_current_but_never_creates_human_evidence(self):
        engine = CurrentEvidenceEngine(*THRESHOLDS)
        for end in (4,8,12): self.add(engine, 30, end)
        fresh = engine.snapshot(12)
        stale = engine.snapshot(30)
        self.assertTrue(fresh["recent_ai"])
        self.assertEqual(stale["freshness"], "stale")
        self.assertEqual(stale["state"], "analyzing")
        self.assertIsNone(stale["score"])
        self.assertFalse(stale["recent_ai"])
        self.assertTrue(stale["historical_warning_events"])
        self.assertFalse(stale["historical_warning_events"][-1]["current"])
        self.assertLess(stale["evidence_start_sec"], stale["evidence_end_sec"])

    def test_silence_does_not_turn_mixed_ai_evidence_into_human(self):
        engine = CurrentEvidenceEngine(*THRESHOLDS)
        for end in (4,8,12): self.add(engine, 30, end)
        self.add(engine, -2, 16)
        before = engine.snapshot(16)
        later = engine.snapshot(29)
        self.assertEqual(later["state"], before["state"])
        self.assertEqual(later["score"], before["score"])
        self.assertEqual(later["evidence_age_sec"], 13)
        self.assertEqual(engine.snapshot(32)["state"], "analyzing")

    def test_overlapping_windows_count_only_new_usable_audio(self):
        engine = CurrentEvidenceEngine(*THRESHOLDS)
        engine.update(1, 30, start_sec=0, end_sec=4)
        second = engine.update(1, 30, start_sec=1, end_sec=5)
        self.assertEqual(second["usable_sec"], 5)
        with self.assertRaises(ValueError): engine.update(1, 30, start_sec=1, end_sec=5)
        for invalid in (math.nan, math.inf, -1):
            with self.assertRaises(ValueError): engine.snapshot(invalid)

    def test_default_flags_do_not_adopt_candidate_policy(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(ScoringConfig.from_env(), ScoringConfig())
        with self.assertRaises(ValueError): ScoringConfig(current_enabled=True)
        with self.assertRaises(ValueError): ScoringConfig(horizon_sec=math.nan)

    def test_timeout_never_counts_late_result_and_failure_preserves_history(self):
        detector = type("Detector", (), {"meta": {"window_sec": 4}})()
        session = AudioScoringSession(detector, THRESHOLDS, sample_rate=100)
        frame = np.full(400, 5000, dtype=np.int16).tobytes()
        session.push(frame, 4)
        _, generation = session.snapshot(4)
        session.complete({"p_fake": 1, "logit": 30, "infer_ms": 1}, generation, now=4.1)
        session.push(frame, 8)
        _, generation = session.snapshot(8)
        timeout = session.payload(19)
        self.assertEqual(timeout["assessment"]["status_reason"], "inference_timeout")
        self.assertIsNone(session.snapshot(19))
        self.assertFalse(session.complete({"p_fake": 0, "logit": -2, "infer_ms": 1}, generation, now=19))
        self.assertEqual(session.risk.n_updates, 1)
        self.assertIn("previous_deepfake", session.payload(19))
        self.assertEqual(session.payload(19)["assessment"]["whole_call_score"], 98.2)
        session.close()
        self.assertFalse(session.complete({}, generation, now=20))

    def test_actual_fixture_generator_matches_saved_packets(self):
        from tools.build_contract_fixtures import build
        path = Path(__file__).with_name("docs") / "evidence-v2-fixtures.json"
        self.assertEqual(json.loads(path.read_text()), build())
        for case in build()["cases"]:
            self.assertLess(len(json.dumps(case["payload"])), 16384)


class QualityTests(unittest.TestCase):
    def feed(self, window, audio, chunks=320):
        pcm = np.clip(audio * 32768, -32768, 32767).astype(np.int16)
        for i in range(0, len(pcm), chunks): window.push_int16(pcm[i:i+chunks].tobytes())

    def test_silence_hiss_pure_tone_and_clipping_do_not_reach_candidate(self):
        rng = np.random.default_rng(22)
        t = np.arange(64000) / 16000
        controls = [(np.zeros(64000), "insufficient_speech"),
                    (rng.normal(0, .02, 64000), "audio_too_noisy"),
                    (.05*np.sin(2*np.pi*440*t), "audio_too_noisy"),
                    (np.ones(64000), "audio_distorted")]
        for audio, reason in controls:
            window = VoicedWindow(gate_mode="adaptive")
            self.feed(window, audio)
            self.assertFalse(window.ready())
            self.assertEqual(window.rejection_reason, reason)

    def test_partial_frame_chunking_does_not_change_eligibility_or_waveform(self):
        rng = np.random.default_rng(1)
        audio = rng.normal(0, .02, 64137)
        a,b = VoicedWindow(gate_mode="adaptive"), VoicedWindow(gate_mode="adaptive")
        self.feed(a, audio, 320)
        self.feed(b, audio, 137)
        self.assertEqual(a.total_seen, b.total_seen)
        self.assertEqual(a.weight, b.weight)
        np.testing.assert_array_equal(a.snapshot(), b.snapshot())
        self.assertEqual(a.diagnostics(), b.diagnostics())

    def test_fixed_gate_threshold_and_clipping_boundaries_are_unchanged(self):
        window = VoicedWindow(sample_rate=100)
        window.push_int16(np.full(400, 328, dtype=np.int16).tobytes())
        self.assertTrue(window.ready())
        window.push_int16(np.full(400, 327, dtype=np.int16).tobytes())
        self.assertFalse(window.ready())
        with self.assertRaises(ValueError): window.push_int16(b"x")


class IntegrityTests(unittest.TestCase):
    def test_hash_mismatch_fails_before_checkpoint_load(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/"best.pt").write_bytes(b"not a real checkpoint")
            (root/"detector_config.json").write_text("{}")
            architecture = Path(__file__).resolve().parents[1]/"architecture/config.json"
            manifest = {"sha256": {"architecture": sha256(architecture),
                        "checkpoint": sha256(root/"best.pt"), "detector_config":sha256(root/"detector_config.json")},
                        "architecture_revision":"test"}
            (root/"pin.json").write_text(json.dumps(manifest))
            self.assertIn("sha256", verify_bundle(root, manifest_path=root/"pin.json"))
            (root/"best.pt").write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "checkpoint"):
                verify_bundle(root, manifest_path=root/"pin.json")


if __name__ == "__main__": unittest.main()
