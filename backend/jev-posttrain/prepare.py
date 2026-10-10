"""Build a reproducible, leakage-checked call-level Jev experiment.

Only published binary scam labels become scam targets. They are not treated as
labels for the ten caller-behavior propositions in the iOS app.
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "prepared"
SEED = 20261008
PROPOSITION = "The caller is attempting to scam or defraud the other person."
LABELS = [f"true: {PROPOSITION}", f"false: not {PROPOSITION}", "insufficient evidence"]


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def key(text: str) -> str:
    return hashlib.sha256(normalize(text).casefold().encode()).hexdigest()


def record(text: str, label: int, source: str, split: str) -> dict:
    text = normalize(text)
    return {"text": text, "target": int(label), "source": source, "split": split, "sha256": key(text)}


def read_csv(path: Path, source: str, split: str) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return [record(r["dialogue"], int(r["label"]), source, split) for r in csv.DictReader(f)]


def read_shake(split: str) -> list[dict]:
    path = RAW / "shake" / "data" / f"{split}-00000-of-00001.parquet"
    table = pq.read_table(path, columns=["dialogue", "label"])
    return [record(t, y, "shake", split) for t, y in zip(table["dialogue"].to_pylist(), table["label"].to_pylist(), strict=True)]


def to_jev(r: dict) -> dict:
    return {
        "id": r["sha256"],
        "domain": "phone_scam",
        "question": "",
        "text": f"Context:\n{r['text']}\n\nEvaluate proposition: {PROPOSITION}",
        "candidates": [{"id": name, "description": desc} for name, desc in zip(("true", "false", "__insufficient_evidence__"), LABELS, strict=True)],
        "target_id": "true" if r["target"] else "false",
        "is_abstention": False,
        "source": r["source"],
        "text_sha256": r["sha256"],
    }


def dump_jsonl(path: Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main() -> None:
    rng = random.Random(SEED)
    OUT.mkdir(parents=True, exist_ok=True)
    groups = {
        "mena_train": read_csv(RAW / "menaattia" / "train_dataset.csv", "menaattia", "train"),
        "mena_test": read_csv(RAW / "menaattia" / "test_dataset.csv", "menaattia", "test"),
        "bosu_train": read_csv(RAW / "bothbosu_scam" / "scam-dialogue_train.csv", "bothbosu", "train"),
        "bosu_test": read_csv(RAW / "bothbosu_scam" / "scam-dialogue_test.csv", "bothbosu", "test"),
        "shake_train": read_shake("train"),
        "shake_val": read_shake("validation"),
        "shake_test": read_shake("test"),
    }
    # The creators' split assignment is authoritative. Drop exact duplicates,
    # preserving held-out rows first so they can never enter training.
    order = ["mena_test", "bosu_test", "shake_test", "shake_val", "mena_train", "bosu_train", "shake_train"]
    seen = set()
    dropped = Counter()
    for name in order:
        unique = []
        for r in groups[name]:
            if r["sha256"] in seen:
                dropped[name] += 1
                continue
            seen.add(r["sha256"])
            unique.append(r)
        groups[name] = unique

    train = groups["mena_train"] + groups["bosu_train"] + groups["shake_train"]
    val = groups["shake_val"]
    test = groups["mena_test"] + groups["bosu_test"] + groups["shake_test"]
    assert not ({r["sha256"] for r in train} & {r["sha256"] for r in val + test})
    rng.shuffle(train)
    dump_jsonl(OUT / "train.jsonl", [to_jev(r) for r in train])
    dump_jsonl(OUT / "validation.jsonl", [to_jev(r) for r in val])
    dump_jsonl(OUT / "test.jsonl", [to_jev(r) for r in test])
    manifest = {
        "seed": SEED,
        "proposition": PROPOSITION,
        "label_contract": "Published whole-call binary labels only; no ten-signal labels inferred",
        "counts": {k: len(v) for k, v in groups.items()},
        "label_counts": {k: dict(Counter(r["target"] for r in v)) for k, v in groups.items()},
        "dropped_exact_duplicates": dict(dropped),
        "prepared_counts": {"train": len(train), "validation": len(val), "test": len(test)},
        "source_urls": {
            "menaattia": "https://huggingface.co/datasets/menaattia/phone-scam-dataset",
            "bothbosu": "https://huggingface.co/datasets/BothBosu/scam-dialogue",
            "shake": "https://huggingface.co/datasets/shakeleoatmeal/phone-scam-detection-synthetic",
        },
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
