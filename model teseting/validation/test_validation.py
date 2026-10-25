import copy
import json
import unittest
from pathlib import Path

from calibrate import fit, threshold_audit
from manifest import validate
from release_gate import evaluate, upper_bound

HERE = Path(__file__).resolve().parent


def source(sid="s1", partition="development", label="human", groups=None):
    return dict(id=sid, partition=partition, label=label, groups=groups or [sid], parents=[], sha256="a" * 64,
                provenance=dict(origin="fixture", rights="licensed", training_overlap="verified_disjoint", independent_review=True))


class ValidationTests(unittest.TestCase):
    def test_frozen_regressions_are_development(self):
        manifest = json.loads((HERE / "data_manifest.json").read_text())
        self.assertTrue(validate(manifest)["valid"])
        self.assertEqual(len(manifest["regression_cases"]), 18)
        self.assertFalse(validate(manifest)["heldout_ready"])

    def test_renamed_audio_and_speaker_leakage_rejected(self):
        a, b = source(), source("s2", "final_test")
        self.assertFalse(validate({"sources": [a, b]})["valid"])
        b["sha256"] = "b" * 64
        a["groups"] = b["groups"] = ["speaker:one"]
        self.assertFalse(validate({"sources": [a, b]})["valid"])

    def test_derivative_must_inherit_parent_groups(self):
        a, b = source(), source("s2")
        b["parents"] = ["s1"]
        self.assertFalse(validate({"sources": [a, b]})["valid"])

    def test_unverified_heldout_provenance_rejected(self):
        s = source(partition="final_test")
        s["provenance"]["training_overlap"] = "unknown"
        self.assertFalse(validate({"sources": [s]})["valid"])

    def test_zero_false_warnings_need_independent_sample_size(self):
        self.assertGreater(upper_bound(0, 2, .95), .7)
        self.assertGreater(upper_bound(0, 298, .95), .01)
        self.assertLess(upper_bound(0, 299, .95), .01)
        self.assertIsNone(upper_bound(0, 0, .95))

    def test_empty_evidence_cannot_release(self):
        spec = json.loads((HERE / "release_spec.json").read_text())
        r = evaluate({"sources": []}, spec, {"calls": [], "checks": {}})
        self.assertFalse(r["release_allowed"])
        self.assertTrue(any("No independent" in x for x in r["blocking_reasons"]))

    def test_unscored_registered_call_cannot_disappear(self):
        spec = json.loads((HERE / "release_spec.json").read_text())
        r = evaluate({"sources": [source(partition="final_test")]}, spec, {"calls": []})
        self.assertIn("Missing final-test call: s1", r["blocking_reasons"])
        row = dict(source_id="s1", analysis_uncovered=False)
        r = evaluate({"sources": [source(partition="final_test")]}, spec, {"calls": [row]})
        self.assertEqual(r["metrics"]["human_false_warning"]["failures"], 1)
        self.assertTrue(any("unknown outcomes" in x for x in r["blocking_reasons"]))

    def test_threshold_audit_does_not_treat_float32_name_as_rate(self):
        audit = threshold_audit({"threshold_eer": 1 - 160 * 2**-24, "threshold_1pct_fpr": 1 - 2 * 2**-24})
        self.assertEqual(audit["thresholds"]["threshold_1pct_fpr"]["float32_steps_below_one"], 2)
        self.assertTrue(audit["no_recalibration_performed"])

    def test_calibration_rejects_development_and_empty_rows(self):
        with self.assertRaises(ValueError):
            fit({"sources": [source()]}, [dict(source_id="s1", logit=1.)], "a" * 64)
        with self.assertRaises(ValueError):
            fit({"sources": []}, [], "a" * 64)

    def test_float64_calibration_preserves_call_weights(self):
        a, b = source(partition="calibration"), source("s2", "calibration", "ai")
        b["sha256"] = "b" * 64
        rows = [dict(source_id="s1", logit=-2., checkpoint_sha256="a" * 64),
                dict(source_id="s2", logit=2., checkpoint_sha256="a" * 64)]
        first = fit({"sources": [a, b]}, rows, "a" * 64)
        repeated = fit({"sources": [a, b]}, rows[:1] * 50 + rows[1:], "a" * 64)
        self.assertAlmostEqual(first["a"], repeated["a"], places=5)
        self.assertAlmostEqual(first["b"], repeated["b"], places=5)
        self.assertFalse(first["population_calibration_established"])


if __name__ == "__main__":
    unittest.main()
