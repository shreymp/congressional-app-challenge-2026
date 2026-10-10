"""Stress-test a Jev scam checkpoint on unseen ICFD-31k synthetic calls.

ICFD's official validation/test conversations contain no clear normal cases,
so clear normal examples come from its train split. Jev was not trained on any
ICFD data in this experiment. This is a cross-source stress test, not a clean
ICFD benchmark or a real-call performance estimate.
"""

from __future__ import annotations

import argparse
import glob
import json
import random
from pathlib import Path

import numpy as np
import torch
import zstandard as zstd
from gliclass import GLiClassModel
from transformers import AutoTokenizer

from evaluate import binary_metrics, sigmoid
from train import HERE, ROOT, encode_rows, predict


def load(split: str, case: str, verdict: str, count: int, seed: int) -> list[dict]:
    base = HERE / "data" / "raw" / "icfd31k" / "source_conversations"
    selected = []
    for path in sorted(glob.glob(str(base / f"{split}-*.jsonl.zst"))):
        with zstd.open(path, "rt", encoding="utf-8") as f:
            for line in f:
                row = json.loads(line)
                if row.get("scenario", {}).get("case_type") != case or row.get("final_verdict") != verdict:
                    continue
                dialogue = "\n".join(f"{t['speaker']}: {t['text']}" for t in row["transcript"])
                selected.append({
                    "text": "Context:\n" + dialogue + "\n\nEvaluate proposition: The caller is attempting to scam or defraud the other person.",
                    "target_id": "true" if verdict == "YES" else "false",
                    "source": f"icfd_{case.lower().replace(' ', '_')}",
                    "text_sha256": str(row.get("scenario", {}).get("scenario_id")) + ":" + str(row.get("generation_metadata", {}).get("combination_key")),
                })
    random.Random(seed).shuffle(selected)
    return selected[:count]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--candidate", type=Path, default=HERE / "runs" / "call-v1")
    p.add_argument("--output", type=Path, default=HERE / "runs" / "ood-evaluation.json")
    p.add_argument("--per-class", type=int, default=500)
    args = p.parse_args()
    examples = load("train", "Clear Normal", "NO", args.per_class, 123) + load("test", "Clear Fraud", "YES", args.per_class, 456)
    print(f"ICFD examples: {len(examples)}; class counts: {sum(r['target_id']=='true' for r in examples)} fraud", flush=True)
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    report = {"dataset": "rishia2220/icfd-31k", "selection": "500 clear-normal train-split calls plus 500 clear-fraud test-split calls, with final verdict matching case type; no ICFD data used for Jev training", "models": {}}
    for name, path in (("base", ROOT / "verdict-151m"), ("candidate", args.candidate)):
        print(f"Evaluating {name}", flush=True)
        tokenizer = AutoTokenizer.from_pretrained(path)
        model = GLiClassModel.from_pretrained(path).to(device)
        encoded = encode_rows(examples, tokenizer, 300)
        logits, y = predict(model, encoded, tokenizer, device, 12)
        # Deliberately use the fixed 0.5 threshold and no ICFD-fitted calibrator.
        scores = sigmoid(logits[:, 0] - logits[:, 1])
        overall = binary_metrics(y, scores)
        report["models"][name] = {"checkpoint": str(path), "overall": overall,
            "clear_normal": binary_metrics(y[:args.per_class], scores[:args.per_class]),
            "clear_fraud": binary_metrics(y[args.per_class:], scores[args.per_class:])}
        print(json.dumps(report["models"][name], indent=2), flush=True)
        del model
        if device.type == "mps": torch.mps.empty_cache()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
