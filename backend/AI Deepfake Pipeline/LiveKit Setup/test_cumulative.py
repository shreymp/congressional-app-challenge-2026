"""Behavioral regressions for bounded call evidence and distinct contiguous audio."""
import math
import unittest

import numpy as np
from audio_window import VoicedWindow
from risk import CallEvidenceEngine, sigmoid
from scoring import AudioScoringSession

THRESHOLDS = (.9999904632568359, .9999998807907104)


class CumulativeTests(unittest.TestCase):
    def engine(self):
        return CallEvidenceEngine(*THRESHOLDS)

    def add(self, engine, z, count=1):
        for _ in range(count):
            result = engine.update(sigmoid(z), z)
        return result

    def test_consistent_speech_gets_early_verdict_with_score(self):
        for z, expected in [(-2, "human"), (30, "ai")]:
            engine = self.engine()
            self.assertEqual(self.add(engine, z)["state"], "analyzing")
            result = self.add(engine, z)
            self.assertEqual(result["state"], expected)
            self.assertTrue(0 <= result["score"] <= 100)
            self.assertEqual(result["score_kind"], "heuristic")

    def test_one_opposing_segment_cannot_erase_established_evidence(self):
        for initial, anomaly, expected in [(-2, 1e6, "human"), (30, -1e6, "ai")]:
            engine = self.engine()
            before = self.add(engine, initial, 3)
            after = self.add(engine, anomaly)
            self.assertEqual(after["state"], expected)
            self.assertNotEqual(before["score"], after["score"])
            self.assertEqual(after["updates"], 4)

    def test_extreme_model_outliers_have_bounded_influence(self):
        values = []
        for z in [100, 1e6]:
            engine = self.engine()
            self.add(engine, -2, 3)
            values.append(self.add(engine, z)["score"])
        self.assertEqual(*values)

    def test_mixed_evidence_is_inconclusive_and_can_recover(self):
        engine = self.engine()
        self.add(engine, -2)
        self.assertEqual(self.add(engine, 30)["state"], "uncertain")
        self.assertEqual(self.add(engine, -2, 4)["state"], "human")

    def test_recent_switch_is_not_hidden_by_long_human_introduction(self):
        engine = self.engine()
        self.add(engine, -2, 100)
        result = self.add(engine, 30, 3)
        self.assertEqual(result["state"], "human")
        self.assertTrue(result["recent_ai"])
        self.assertEqual(result["max_ai_run"], 3)
        result = self.add(engine, -2, 5)
        self.assertFalse(result["recent_ai"])
        self.assertEqual(result["max_ai_run"], 3)

    def test_quality_weight_changes_influence_without_inventing_confidence(self):
        engine = self.engine()
        self.add(engine, -2, 3)
        low_quality = engine.update(1, 30, .4)
        other = self.engine()
        self.add(other, -2, 3)
        self.assertLess(low_quality["score"], self.add(other, 30)["score"])
        for p, z, weight in [(math.nan, 1, 1), (.5, math.inf, 1), (.5, 1, 0), (.5, 1, 2)]:
            with self.assertRaises(ValueError):
                engine.update(p, z, weight)

    def test_audio_preserves_pauses_and_rejects_clipping(self):
        window = VoicedWindow(sample_rate=100, window_sec=4)
        window.push_int16(np.full(200, 5000, dtype=np.int16).tobytes())
        window.push_int16(bytes(400))
        self.assertTrue(window.ready())
        self.assertEqual(window.weight, .5)
        self.assertTrue(np.all(window.snapshot()[-200:] == 0))
        window.push_int16(np.full(400, 32767, dtype=np.int16).tobytes())
        self.assertFalse(window.ready())

    def test_duplicate_and_retired_inference_cannot_count_twice(self):
        detector = type("Detector", (), {"meta": {"window_sec": 4}})()
        session = AudioScoringSession(detector, THRESHOLDS, sample_rate=100)
        frame = np.full(400, 5000, dtype=np.int16).tobytes()
        session.push(frame, 4)
        _, first = session.snapshot(4)
        result = {"p_fake": 0, "logit": -2, "infer_ms": 1}
        session.complete(result, first)
        session.complete(result, first)
        self.assertEqual(session.risk.n_updates, 1)
        session.push(frame, 8)
        _, second = session.snapshot(8)
        session.complete(result, first)
        self.assertIsNotNone(session.pending_since)
        session.complete(result, second)
        self.assertEqual(session.risk.n_updates, 2)


if __name__ == "__main__":
    unittest.main()
