"""Check whether scam fine-tuning damaged Jev's original decision task."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch
from gliclass import GLiClassModel
from transformers import AutoTokenizer

from train import HERE, ROOT


def evaluate(model_dir: Path, records: list[dict], device: torch.device) -> dict:
    tokenizer = AutoTokenizer.from_pretrained(model_dir)
    model = GLiClassModel.from_pretrained(model_dir).to(device).eval()
    correct, nll, total = 0, 0.0, 0
    with torch.no_grad():
        for r in records:
            labels = [c["description"] for c in r["candidates"]]
            prefix = "".join(f"<<LABEL>>{s}" for s in labels)
            prompt = f"{prefix}<<SEP>>Question: {r['question']}\n\nContext:\n{r['text']}" if r["question"] else f"{prefix}<<SEP>>{r['text']}"
            tokens = tokenizer(prompt, truncation=True, max_length=512, return_tensors="pt").to(device)
            logits = model(**tokens).logits[0, :len(labels)].float()
            target = next(i for i, c in enumerate(r["candidates"]) if c["id"] == r["target_id"])
            probs = torch.softmax(logits, dim=-1)
            correct += int(logits.argmax().item() == target)
            nll -= float(torch.log(probs[target].clamp_min(1e-8)).item())
            total += 1
    return {"n": total, "accuracy": correct / total, "nll": nll / total}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--candidate", type=Path, default=HERE / "runs" / "call-v1")
    p.add_argument("--upstream-validation", type=Path, default=HERE / "data" / "raw" / "upstream_jev" / "val.jsonl")
    p.add_argument("--output", type=Path, default=HERE / "runs" / "retention.json")
    args = p.parse_args()
    rows = [json.loads(s) for s in args.upstream_validation.read_text().splitlines() if s]
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    report = {}
    for name, path in (("base", ROOT / "verdict-151m"), ("candidate", args.candidate)):
        print(f"Evaluating {name} on {len(rows)} original decision examples", flush=True)
        report[name] = evaluate(path, rows, device)
        print(json.dumps(report[name]), flush=True)
        if device.type == "mps": torch.mps.empty_cache()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
