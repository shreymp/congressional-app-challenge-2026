import csv, json, sys, tempfile, unittest
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import calibrate

class CalibrateTests(unittest.TestCase):
    def write(self, folder, rows):
        path = Path(folder) / "per_window.csv"
        with path.open("w", newline="") as f:
            w = csv.DictWriter(f, ["case", "selection", "completed", "logit", "weight"]); w.writeheader()
            for r in rows: w.writerow(r)
        return path

    def test_recovers_platt_parameters_and_binds_checkpoint(self):
        rng = np.random.default_rng(0); rows = []
        a, b = .8, -12.0
        for src in range(4):
            for label in ("ai", "human"):
                z = rng.normal(15, 6, 400)
                keep = rng.random(400) < 1 / (1 + np.exp(-(a * z + b)))
                for zi, k in zip(z, keep):
                    if (label == "ai") == bool(k):
                        rows.append(dict(case=f"{label}{src}", selection="current", completed="True", logit=zi, weight=1))
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, rows)
            labels = Path(tmp) / "labels.csv"
            labels.write_text("case,label,source,split\n" + "".join(
                f"{l}{s},{l},{l}{s},dev\n" for s in range(4) for l in ("ai", "human")))
            out = Path(tmp) / "cal.json"
            calibrate.main(["--windows", str(path), "--labels", str(labels), "--checkpoint-sha256", "ab" * 32,
                            "--output", str(out)])
            d = json.loads(out.read_text())
            self.assertEqual(d["status"], "development")
            self.assertEqual(d["checkpoint_sha256"], "ab" * 32)
            # Class balancing changes the intercept, not the slope.
            self.assertAlmostEqual(d["platt"]["a"], a, delta=.15)
            with self.assertRaises(SystemExit):   # never overwrite
                calibrate.main(["--windows", str(path), "--labels", str(labels), "--checkpoint-sha256", "ab" * 32, "--output", str(out)])
            with self.assertRaises(SystemExit):   # release needs held-out data and enough sources
                calibrate.main(["--windows", str(path), "--labels", str(labels), "--checkpoint-sha256", "ab" * 32,
                                "--output", str(Path(tmp) / "r.json"), "--release"])

    def test_auto_labels_exclude_mixed_and_control_cases(self):
        self.assertIsNone(calibrate.auto_label("control_dtmf_rms0.03"))
        self.assertIsNone(calibrate.auto_label("human60_then_ai"))
        self.assertEqual(calibrate.auto_label("librispeech_test_clean_1320_40s__g711_mulaw")[:2], ("human", "librispeech_test_clean_1320_40s"))
        self.assertEqual(calibrate.auto_label("white_noise_10dB_SNR")[0], "ai")

if __name__ == "__main__":
    unittest.main()
