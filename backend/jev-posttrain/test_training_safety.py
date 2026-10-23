"""Regression tests for failure modes that produced the V6 conservative shift."""
import json
import hashlib
import tempfile
import unittest
from pathlib import Path

from training_safety import (audit_splits, balanced_parent_weights, domain,
                             fit_operating_point, parent_domain_nll, regression_gate, validate_decision_policy)


def row(identity, scam=False, source="recorded", **kwargs):
    return {"id": identity, "text": "words for " + identity, "source": source,
            "target_id": "true" if scam else "false", "label": int(scam), **kwargs}


class TrainingSafetyTests(unittest.TestCase):
    def test_prefix_explosion_does_not_change_class_or_parent_mass(self):
        base = [row("scam", True), row("normal"), row("other")]
        more = base + [row(f"prefix{i}", parent_id="normal", source="recorded_prefix") for i in range(100)]
        weights, report = balanced_parent_weights(more)
        self.assertAlmostEqual(sum(w for r, w in zip(more, weights) if r["label"]), len(more) / 2)
        normal_mass = sum(w for r, w in zip(more, weights) if r.get("parent_id", r["id"]) == "normal")
        self.assertAlmostEqual(normal_mass, weights[2])
        self.assertEqual(report["parents"], 3)

    def test_conflicting_parent_labels_and_single_class_rejected(self):
        with self.assertRaises(ValueError):
            balanced_parent_weights([row("a"), row("a", True)])
        with self.assertRaises(ValueError):
            balanced_parent_weights([row("a")])

    def test_better_average_loss_cannot_hide_added_missed_scam(self):
        rows = [row("fraud", True)] + [row(str(i)) for i in range(10)]
        baseline, candidate = [.8] + [.6] * 10, [.4] + [.01] * 10
        self.assertLess(parent_domain_nll(rows, candidate), parent_domain_nll(rows, baseline))
        gate = regression_gate(rows, baseline, candidate)
        self.assertFalse(gate["passed"])
        self.assertTrue(any("fn increased" in r for r in gate["failures"]))

    def test_one_domain_cannot_hide_regression_in_another(self):
        rows = [row("a", True, "bank"), row("b", True, "government")]
        gate = regression_gate(rows, [.9, .4], [.4, .9])
        self.assertFalse(gate["passed"])
        self.assertTrue(any("source:bank" in r for r in gate["failures"]))

    def test_prefix_validation_counts_parent_once(self):
        rows = [row("a", True), row("b"), row("bp", parent_id="b", source="recorded_prefix")]
        gate = regression_gate(rows, [.9, .1, .1], [.9, .1, .2])
        self.assertTrue(gate["passed"])
        self.assertEqual(gate["groups"]["all@0.5"]["candidate"]["n"], 2)
        self.assertEqual(domain(rows[-1]), "recorded")

    def test_nan_prefix_cannot_disappear_during_parent_pooling(self):
        rows = [row("a", True), row("b"), row("bp", parent_id="b", source="recorded_prefix")]
        with self.assertRaises(ValueError):
            regression_gate(rows, [.9, .1, .1], [.9, .1, float("nan")])

    def test_parent_domain_loss_invariant_to_duplicate_prefix_vote(self):
        rows = [row("a", True), row("b", source="bank")]
        duplicate = row("bp", source="bank_prefix", parent_id="b")
        self.assertAlmostEqual(parent_domain_nll(rows, [.9, .1]),
                               parent_domain_nll(rows + [duplicate], [.9, .1, .1]))

    def test_split_audit_rejects_parent_script_speaker_and_text_leaks(self):
        pairs = [(row("a"), row("b", parent_id="a", source="recorded_prefix")),
                 (row("a", group="script"), row("b", group="script")),
                 (row("a", speakers=["person"]), row("b", speakers=["person"])),
                 (row("a"), row("b", text="WORDS FOR A!"))]
        for a, b in pairs:
            with self.subTest(a=a, b=b), self.assertRaises(ValueError):
                audit_splits([a], [b])

    def test_fit_fails_closed_when_recall_and_false_alerts_conflict(self):
        result = fit_operating_point([row("a", True), row("b")], [.1, .9])
        self.assertFalse(result["passed"])
        self.assertIsNone(result["threshold"])

    def test_fit_checks_each_benign_domain_not_just_average(self):
        rows = [row("scam", True), row("bank", source="bank")] + [row(str(i)) for i in range(100)]
        result = fit_operating_point(rows, [.8, .9] + [.01] * 100)
        self.assertFalse(result["passed"])

    def test_fit_uses_validation_cutoff_and_rejects_invalid_scores(self):
        rows = [row("a", True), row("b")]
        result = fit_operating_point(rows, [.1, .001])
        self.assertTrue(result["passed"])
        self.assertAlmostEqual(result["threshold"], .1)
        with self.assertRaises(ValueError):
            fit_operating_point(rows, [float("nan"), .1])

    def test_numpy_inference_outputs_produce_serializable_audit(self):
        import numpy as np
        rows = [row("a", True), row("b")]
        result = regression_gate(rows, np.array([.9, .1]), np.array([.95, .05]))
        self.assertTrue(json.loads(json.dumps(result))["passed"])

    def test_policy_rejects_failed_nan_and_wrong_model_or_temperature(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "model.safetensors").write_bytes(b"one exact model")
            (directory / "tokenizer.json").write_text("{}")
            (directory / "calibration.json").write_text('{"temperature": 2.0}')
            policy = {"passed": True, "threshold": .01, "temperature": 2.0,
                      "context_mode": "windows", "research_only": True,
                      "checkpoint_sha256": hashlib.sha256(b"one exact model").hexdigest(),
                      "tokenizer_sha256": hashlib.sha256(b"{}").hexdigest()}
            validate_decision_policy(policy, directory)
            for changed in ({"passed": False}, {"threshold": float("nan")},
                            {"temperature": 1.0}, {"checkpoint_sha256": "wrong"},
                            {"context_mode": "tail"}, {"tokenizer_sha256": "wrong"}):
                with self.subTest(changed=changed), self.assertRaises(ValueError):
                    validate_decision_policy(policy | changed, directory)


if __name__ == "__main__":
    unittest.main()
