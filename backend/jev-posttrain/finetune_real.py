"""Continue Jev training on public recorded-call text plus synthetic replay.

Never reads the test split. Uses class/call-balanced training and rejects
validation regressions before selecting by parent/domain loss. Writes a separate
research checkpoint; export and deployment require separate evaluation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import time
from pathlib import Path

import numpy as np
import torch
from gliclass import GLiClassModel
from safetensors.torch import save_file
from transformers import AutoTokenizer

from train import HERE, DATA, PROPOSITION, caller_only, encode_rows, read_jsonl, batch_tensors, predict
from evaluate import binary_metrics, sigmoid, temperature_from_validation
from training_safety import (audit_splits, balanced_parent_weights, domain,
                             parent_domain_nll, regression_gate)


def as_training(rows):
    if any(r["label"] not in (0, 1) for r in rows):
        raise ValueError("Recorded rows require explicit binary labels; ambiguous prefixes need separate adjudication")
    return [{"text": "Context:\n" + r["text"] + "\n\nEvaluate proposition: " + PROPOSITION,
             "target_id": "true" if r["label"] else "false", "source": r["source"],
             "text_sha256": r["id"], "parent_id": r.get("parent_id", r["id"]),
             **{k: r[k] for k in ("group", "speakers", "validation_domain") if k in r}} for r in rows]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", type=Path, default=HERE / "runs/call-v2-caller")
    p.add_argument("--data", type=Path, default=HERE / "data/real_calls")
    p.add_argument("--output", type=Path, required=True, help="New research directory; existing runs cannot be overwritten")
    p.add_argument("--epochs", type=int, default=2)
    p.add_argument("--replay", type=int, default=600)
    p.add_argument("--lr", type=float, default=3e-6)
    p.add_argument("--extra-train", type=Path)
    p.add_argument("--extra-validation", type=Path)
    p.add_argument("--domain-balanced-selection", action="store_true", help="Compatibility option: parent/domain-balanced selection is now always enabled")
    args = p.parse_args()
    if args.output.exists():
        p.error("Output exists; use a new directory to preserve earlier evidence")
    seed = 20261020
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
    torch.set_num_threads(4)
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
    model = GLiClassModel.from_pretrained(args.model, local_files_only=True).to(device)
    real = as_training(read_jsonl(args.data / "train.jsonl"))
    replay = [caller_only(r) for r in read_jsonl(DATA / "train.jsonl") if "caller:" in r["text"].lower()]
    random.shuffle(replay)
    train_raw = real + replay[:args.replay]
    extra_train = as_training(read_jsonl(args.extra_train)) if args.extra_train else []
    train_raw += extra_train
    # Robustness augmentation is training-only; never counted as real examples.
    augmented = []
    for r in real:
        item = dict(r)
        raw = r["text"].split("Context:\n", 1)[1].rsplit("\n\nEvaluate proposition:", 1)[0]
        import re
        raw = re.sub(r"[^\w\s]", " ", raw.lower())
        words = raw.split()
        raw = " ".join(w for w in words if random.random() > .04)
        item["text"] = "Context:\nCaller: " + raw + "\n\nEvaluate proposition: " + PROPOSITION
        augmented.append(item)
    presentations = train_raw + augmented
    weights, weighting = balanced_parent_weights(presentations)
    train = encode_rows(presentations, tokenizer, 300)
    for row, weight in zip(train, weights):
        row["weight"] = weight
    validation_raw = as_training(read_jsonl(args.data / "validation.jsonl"))
    extra_val = as_training(read_jsonl(args.extra_validation)) if args.extra_validation else []
    # Replay validation protects against erasing earlier scam families.
    synthetic_val = [caller_only(r) for r in read_jsonl(DATA / "validation.jsonl") if "caller:" in r["text"].lower()]
    raw_val = validation_raw + synthetic_val + extra_val
    split_audit = audit_splits(presentations, raw_val)
    val = encode_rows(raw_val, tokenizer, 300)
    start = time.monotonic()
    args.output.mkdir(parents=True, exist_ok=True)
    best = float("inf")
    history = []
    selected_epoch = 0
    selected_sha256 = None
    # Keep the baseline's scale fixed during checkpoint comparison. Refitting
    # temperature each epoch could move warning decisions and conceal regressions.
    calibration = args.model / "calibration.json"
    baseline_temperature = json.loads(calibration.read_text())["temperature"] if calibration.exists() else None
    baseline_scores = {}
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=.01)
    print(json.dumps({"device": str(device), "real_training": len(real), "replay": min(args.replay, len(replay)), "augmentation": len(augmented), "extra_training": len(extra_train), "extra_validation": len(extra_val), "validation": len(val)}), flush=True)
    from benchmark_real import infer
    call_val = [{"id": r.get("parent_id", r["text_sha256"]), "label": int(r["target_id"] == "true"),
                 "text": r["text"].split("Context:\n", 1)[1].rsplit("\n\nEvaluate proposition:", 1)[0]}
                for r in raw_val]
    manifest = {"base": str(args.model), "seed": seed, "lr": args.lr,
                "weighting": weighting, "split_audit": split_audit,
                "selection": "fixed baseline temperature; no additional parent-call FN/FP at .5/.75, per original domain, tail AND windows; then parent/domain NLL",
                "real_training": len(real), "augmented_training": len(augmented),
                "extra_training": len(extra_train), "extra_validation": len(extra_val),
                "test_access": "none", "deployment": "research only; separate operating-point validation and fresh evaluation required"}
    for epoch in range(args.epochs + 1):
        if epoch:
            random.shuffle(train)
            model.train()
            optimizer.zero_grad(set_to_none=True)
            for offset in range(0, len(train), 16):
                block = train[offset:offset+16]
                block_loss = 0.0
                for start_batch in range(0, len(block), 4):
                    batch = block[start_batch:start_batch+4]
                    inputs, y = batch_tensors(batch, tokenizer, device)
                    logits = model(**inputs).logits[:, :3].float()
                    losses = torch.nn.functional.cross_entropy(logits, y, reduction="none")
                    w = torch.tensor([r["weight"] for r in batch], device=device)
                    loss = (losses * w).sum() / len(block)
                    loss.backward()
                    block_loss += float(loss.detach().cpu())
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1)
                optimizer.step(); optimizer.zero_grad(set_to_none=True)
                if offset % 160 == 0:
                    print(f"epoch {epoch} examples {offset}/{len(train)} weighted_loss {block_loss:.4f}", flush=True)
        logits, labels = predict(model, val, tokenizer, device, 8)
        if baseline_temperature is None:
            baseline_temperature = temperature_from_validation(logits, labels)
        t = baseline_temperature
        scores = sigmoid((logits[:, 0] - logits[:, 1]) / t)
        measured = binary_metrics(labels, scores)
        hard_metrics = binary_metrics(labels[-len(extra_val):], scores[-len(extra_val):]) if extra_val else None
        source_metrics = {}
        for source in sorted({domain(r) for r in raw_val}):
            indices = [i for i, r in enumerate(raw_val) if domain(r) == source]
            source_metrics[source] = binary_metrics(labels[indices], scores[indices])
        selection_loss = parent_domain_nll(raw_val, scores)
        window_scores = infer(model, tokenizer, call_val, device, t, "windows")
        if epoch == 0:
            baseline_scores = {"tail": list(map(float, scores)), "windows": window_scores}
        gates = {mode: regression_gate(raw_val, baseline_scores[mode], values)
                 for mode, values in (("tail", scores), ("windows", window_scores))}
        eligible = all(g["passed"] for g in gates.values())
        entry = {"epoch": epoch, "temperature": t, "validation": measured,
                 "recorded_validation": binary_metrics(labels[:len(validation_raw)], scores[:len(validation_raw)]),
                 "extra_validation": hard_metrics, "validation_by_source": source_metrics,
                 "selection_loss": selection_loss, "regression_gates": gates,
                 "eligible": eligible, "elapsed_sec": time.monotonic() - start}
        history.append(entry)
        print(json.dumps({k: v for k, v in entry.items() if k != "regression_gates"} |
                         {"gate_failures": {m: g["failures"] for m, g in gates.items()}}), flush=True)
        if eligible and selection_loss < best:
            best = selection_loss
            selected_epoch = epoch
            save_file({k: v.detach().cpu().contiguous() for k,v in model.state_dict().items()}, args.output / "model.safetensors")
            model.config.save_pretrained(args.output)
            tokenizer.save_pretrained(args.output)
            (args.output / "calibration.json").write_text(json.dumps({"temperature": t, "scope": "baseline scale frozen for regression comparison; not field probability calibration", "selected_epoch": epoch}, indent=2)+"\n")
            with (args.output / "model.safetensors").open("rb") as checkpoint:
                selected_sha256 = hashlib.file_digest(checkpoint, "sha256").hexdigest()
        (args.output / "train_manifest.json").write_text(json.dumps(manifest | {"history": history,
            "selected_epoch": selected_epoch, "improved_checkpoint": selected_epoch > 0,
            "selected_checkpoint_sha256": selected_sha256,
            "baseline_retained_if_no_candidate_passes": True}, indent=2)+"\n")


if __name__ == "__main__":
    main()
