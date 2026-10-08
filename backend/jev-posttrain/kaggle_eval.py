"""Evaluate on Kaggle's 800 short calls without training or recalibration."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import torch
from gliclass import GLiClassModel
from transformers import AutoTokenizer

from evaluate import binary_metrics, sigmoid
from train import HERE, PROPOSITION, ROOT, encode_rows, predict


def load() -> list[dict]:
    base = HERE / "data" / "raw" / "kaggle_teeconnie"
    result = []
    for name, target in (("English_NonScam.txt", "false"), ("English_Scam.txt", "true")):
        text = (base / name).read_text(encoding="utf-8-sig")
        for i, part in enumerate(re.split(r"\r?\n\s*\r?\n", text)):
            part = re.sub(r"^\s*\d+\.\s*", "", part.strip())
            if not part:
                continue
            result.append({"text": f"Context:\nCaller: {part}\n\nEvaluate proposition: {PROPOSITION}", "target_id": target, "source": "kaggle_teeconnie", "text_sha256": f"{name}:{i}"})
    return result


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--candidate", type=Path, default=HERE / "runs" / "call-v1")
    p.add_argument("--output", type=Path, default=HERE / "runs" / "call-v1" / "kaggle-evaluation.json")
    args = p.parse_args()
    rows = load()
    assert len(rows) == 800 and sum(r["target_id"] == "true" for r in rows) == 400
    previous = json.loads((args.candidate / "evaluation.json").read_text())
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    report = {"dataset": "https://www.kaggle.com/datasets/teeconnie/scam-and-non-scam-call-conversation-dataset", "evaluation_only": True, "n": 800, "normalization": "Leading numeric indices stripped from scam entries", "models": {}}
    for name, model_path in (("base", ROOT / "verdict-151m"), ("candidate", args.candidate)):
        print(f"Evaluating {name}", flush=True)
        tokenizer = AutoTokenizer.from_pretrained(model_path)
        model = GLiClassModel.from_pretrained(model_path).to(device)
        encoded = encode_rows(rows, tokenizer, 300)
        logits, labels = predict(model, encoded, tokenizer, device, 12)
        temp = float(previous["models"][name]["validation_temperature"])
        scores = sigmoid((logits[:, 0] - logits[:, 1]) / temp)
        report["models"][name] = {"temperature_from_shake_validation": temp, "metrics": binary_metrics(labels, scores)}
        print(json.dumps(report["models"][name], indent=2), flush=True)
        del model
        if device.type == "mps": torch.mps.empty_cache()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
