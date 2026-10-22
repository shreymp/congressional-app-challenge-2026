"""Compare a local Jev scam checkpoint against the unchanged base on held-out calls."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch
from gliclass import GLiClassModel
from transformers import AutoTokenizer

from train import DATA, HERE, ROOT, encode_rows, predict, prepare_prompt, read_jsonl


def sigmoid(values: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-np.clip(values, -30, 30)))


def binary_metrics(y: np.ndarray, p: np.ndarray) -> dict:
    pred = p >= 0.5
    actual = y == 0
    tp, tn, fp, fn = (
        int((pred & actual).sum()), int((~pred & ~actual).sum()),
        int((pred & ~actual).sum()), int((~pred & actual).sum()),
    )
    eps = 1e-8
    nll = -(actual * np.log(np.clip(p, eps, 1 - eps)) + (~actual) * np.log(np.clip(1 - p, eps, 1 - eps))).mean()
    ece = 0.0
    for low in np.linspace(0, 1, 11)[:-1]:
        mask = (p >= low) & (p < low + .1 if low < .9 else p <= 1)
        if mask.any():
            ece += mask.mean() * abs(float(actual[mask].mean()) - float(p[mask].mean()))
    return {
        "n": len(y), "positives": int(actual.sum()), "negatives": int((~actual).sum()),
        "accuracy": (tp + tn) / len(y), "precision": tp / max(1, tp + fp),
        "recall": tp / max(1, tp + fn), "specificity": tn / max(1, tn + fp),
        "f1": 2 * tp / max(1, 2 * tp + fp + fn),
        "brier": float(np.square(p - actual).mean()), "nll": float(nll),
        "ece_10_bin": float(ece), "confusion": {"tp": tp, "tn": tn, "fp": fp, "fn": fn},
    }


def temperature_from_validation(logits: np.ndarray, labels: np.ndarray) -> float:
    diff = logits[:, 0] - logits[:, 1]
    candidates = np.exp(np.linspace(np.log(.25), np.log(8), 150))
    return float(min(candidates, key=lambda t: binary_metrics(labels, sigmoid(diff / t))["nll"]))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--candidate", type=Path, default=HERE / "runs" / "call-v1")
    p.add_argument("--output", type=Path, default=HERE / "runs" / "evaluation.json")
    p.add_argument("--max-context-tokens", type=int, default=300)
    args = p.parse_args()
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    validation = read_jsonl(DATA / "validation.jsonl")
    test = read_jsonl(DATA / "test.jsonl")
    contrasts = [
        ("obvious_code_scam", "Caller: I am from your bank fraud department. Read me the six-digit code we just texted you, and do not tell your bank branch or anyone in your family."),
        ("dentist_reschedule", "Caller: Hi, this is Maple Dental. We need to reschedule your cleaning from Tuesday to Thursday. Does 3 p.m. work for you?"),
    ]
    contrast_rows = [{"text": "Context:\n" + s + "\n\nEvaluate proposition: The caller is attempting to scam or defraud the other person.", "target_id": "true" if i == 0 else "false", "source": "contrast", "text_sha256": name} for i, (name, s) in enumerate(contrasts)]
    report = {"validation_source": "shakeleoatmeal validation", "test_sources": ["menaattia test", "BothBosu test", "shakeleoatmeal test"], "models": {}}
    for name, model_dir in (("base", ROOT / "verdict-151m"), ("candidate", args.candidate)):
        print(f"Loading {name}: {model_dir}", flush=True)
        tokenizer = AutoTokenizer.from_pretrained(model_dir)
        model = GLiClassModel.from_pretrained(model_dir).to(device)
        val_enc = encode_rows(validation, tokenizer, args.max_context_tokens)
        test_enc = encode_rows(test, tokenizer, args.max_context_tokens)
        contrast_enc = encode_rows(contrast_rows, tokenizer, args.max_context_tokens)
        val_logits, val_y = predict(model, val_enc, tokenizer, device, 12)
        temperature = temperature_from_validation(val_logits, val_y)
        test_logits, test_y = predict(model, test_enc, tokenizer, device, 12)
        contrast_logits, _ = predict(model, contrast_enc, tokenizer, device, 2)
        p_val = sigmoid((val_logits[:, 0] - val_logits[:, 1]) / temperature)
        p_test = sigmoid((test_logits[:, 0] - test_logits[:, 1]) / temperature)
        p_contrast = sigmoid((contrast_logits[:, 0] - contrast_logits[:, 1]) / temperature)
        by_source = {}
        for source in sorted({r["source"] for r in test_enc}):
            mask = np.array([r["source"] == source for r in test_enc])
            by_source[source] = binary_metrics(test_y[mask], p_test[mask])
        report["models"][name] = {
            "checkpoint": str(model_dir), "validation_temperature": temperature,
            "validation": binary_metrics(val_y, p_val),
            "test_all": binary_metrics(test_y, p_test), "test_by_source": by_source,
            "contrast": {key: float(score) for (key, _), score in zip(contrasts, p_contrast, strict=True)},
        }
        print(json.dumps(report["models"][name], indent=2), flush=True)
        del model
        if device.type == "mps":
            torch.mps.empty_cache()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Wrote {args.output}", flush=True)


if __name__ == "__main__":
    main()
