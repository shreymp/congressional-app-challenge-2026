"""Logit-space thresholds and checkpoint-bound Platt calibration."""
import json
import math
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import detector_adapter
from current_evidence import CurrentEvidenceEngine
from risk import CallEvidenceEngine, logit, sigmoid

THRESHOLDS = (0.9999904632568359, 0.9999998807907104)
SHA = "ab" * 32


class Det:
    meta = {"threshold_eer": THRESHOLDS[0], "threshold_1pct_fpr": THRESHOLDS[1]}


class CalibrationTests(unittest.TestCase):
    def test_platt_mapping_replaces_center_and_scale(self):
        a, b = .5, -7.0
        engine = CallEvidenceEngine(*THRESHOLDS, calibration={"a": a, "b": b})
        self.assertTrue(engine.calibrated)
        for z in (6.0, 14.0, 20.0):
            out = CallEvidenceEngine(*THRESHOLDS, calibration={"a": a, "b": b}).update(sigmoid(z), z)
            self.assertAlmostEqual(out["score"], round(100 * sigmoid(max(-4, min(4, a * z + b))), 1))
        current = CurrentEvidenceEngine(*THRESHOLDS, calibration={"a": a, "b": b})
        self.assertAlmostEqual(current.center, 14.0)
        self.assertAlmostEqual(current.scale, 2.0)
        with self.assertRaises(ValueError):
            CallEvidenceEngine(*THRESHOLDS, calibration={"a": -1, "b": 0})

    def test_uncalibrated_engine_is_unchanged(self):
        engine = CallEvidenceEngine(*THRESHOLDS)
        self.assertFalse(engine.calibrated)
        self.assertAlmostEqual(engine.center, (logit(THRESHOLDS[0]) + logit(THRESHOLDS[1])) / 2)

    def test_logit_thresholds_take_precedence_in_float64(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            for key in ("THRESHOLD_ELEVATED_LOGIT", "THRESHOLD_HIGH_LOGIT", "THRESHOLD_ELEVATED", "THRESHOLD_HIGH"):
                os.environ.pop(key, None)
            self.assertEqual(detector_adapter.thresholds(Det()), THRESHOLDS)
            det = Det(); det.meta = dict(Det.meta, logit_threshold_eer=12.0, logit_threshold_1pct_fpr=19.5)
            low, high = detector_adapter.thresholds(det)
            self.assertAlmostEqual(logit(low), 12.0, places=6)
            self.assertAlmostEqual(logit(high), 19.5, places=5)
            os.environ["THRESHOLD_HIGH_LOGIT"] = "30"
            with self.assertRaises(ValueError):
                detector_adapter.thresholds(det)

    def test_calibration_file_is_bound_to_checkpoint_and_release_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "calibration.json"
            body = {"schema": "detector-calibration-v1", "checkpoint_sha256": SHA,
                    "status": "development", "platt": {"a": .5, "b": -7}}
            path.write_text(json.dumps(body))
            env = {"CALIBRATION_PATH": str(path)}
            with mock.patch.dict(os.environ, env):
                os.environ.pop("ALLOW_DEV_CALIBRATION", None)
                with self.assertRaises(ValueError):
                    detector_adapter.load_calibration(SHA)
                os.environ["ALLOW_DEV_CALIBRATION"] = "1"
                self.assertEqual(detector_adapter.load_calibration(SHA)["a"], .5)
                with self.assertRaises(ValueError):
                    detector_adapter.load_calibration("cd" * 32)
                os.environ["CALIBRATION"] = "off"
                self.assertIsNone(detector_adapter.load_calibration("cd" * 32))
            # The release-path fitter's candidate format is accepted, but only as non-release.
            path.write_text(json.dumps({"schema_version": 1, "method": "float64_call_weighted_platt", "a": .4, "b": -6,
                                        "checkpoint_sha256": SHA, "status": "candidate_requires_frozen_heldout_validation"}))
            with mock.patch.dict(os.environ, {"CALIBRATION_PATH": str(path)}):
                os.environ.pop("ALLOW_DEV_CALIBRATION", None); os.environ.pop("CALIBRATION", None)
                with self.assertRaises(ValueError):
                    detector_adapter.load_calibration(SHA)
                os.environ["ALLOW_DEV_CALIBRATION"] = "1"
                self.assertEqual(detector_adapter.load_calibration(SHA)["b"], -6.0)
            with mock.patch.dict(os.environ, {"CALIBRATION_PATH": str(Path(tmp) / "missing.json")}):
                self.assertIsNone(detector_adapter.load_calibration(SHA))


if __name__ == "__main__":
    unittest.main()
