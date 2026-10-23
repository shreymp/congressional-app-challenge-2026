import json
import tempfile
import unittest
from pathlib import Path

from benign_prefix_training import build, prefixes


class PrefixDataTests(unittest.TestCase):
    def row(self, identity, label=0, word="normal"):
        return {"id": identity, "label": label, "source": "recorded",
                "text": "Caller: " + " ".join(f"{word}{i}" for i in range(90))}

    def test_scam_call_label_is_not_copied_to_prefix(self):
        self.assertEqual(prefixes([self.row("fraud", 1)]), [])

    def test_prefixes_keep_parent_and_are_shorter(self):
        row = self.row("normal")
        got = prefixes([row])
        self.assertEqual(len(got), 2)
        self.assertTrue(all(r["parent_id"] == "normal" and r["label"] == 0 for r in got))
        self.assertTrue(all(len(r["text"]) < len(row["text"]) for r in got))

    def test_train_validation_parent_leakage_rejected_without_test_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            (data / "banking_training").mkdir(parents=True)
            for split in ("train", "validation"):
                (data / f"{split}.jsonl").write_text(json.dumps(self.row("same")) + "\n")
                (data / "banking_training" / f"{split}.jsonl").write_text("")
            with self.assertRaises(ValueError):
                build(data, Path(tmp) / "output")

    def test_build_reads_only_train_validation_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            (data / "banking_training").mkdir(parents=True)
            for split in ("train", "validation"):
                (data / f"{split}.jsonl").write_text(json.dumps(self.row(split, word=split)) + "\n")
                (data / "banking_training" / f"{split}.jsonl").write_text("")
            output = Path(tmp) / "output"
            self.assertEqual(build(data, output)["counts"], {"train": 2, "validation": 2})
            with self.assertRaises(FileExistsError):
                build(data, output)


if __name__ == "__main__":
    unittest.main()
