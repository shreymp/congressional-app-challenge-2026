"""Continue Jev training on public recorded-call text plus synthetic replay.

Never reads the test split. Selects by validation loss; writes a separate research
checkpoint. Data/weights stay local. Export and deployment are separate steps.
"""
from __future__ import annotations

import argparse
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


def as_training(rows):
    return [{"text": "Context:\n" + r["text"] + "\n\nEvaluate proposition: " + PROPOSITION,
             "target_id": "true" if r["label"] else "false", "source": r["source"],
             "text_sha256": r["id"]} for r in rows]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", type=Path, default=HERE / "runs/call-v2-caller")
    p.add_argument("--data", type=Path, default=HERE / "data/real_calls")
    p.add_argument("--output", type=Path, default=HERE / "runs/call-v3-real")
    p.add_argument("--epochs", type=int, default=2)
    p.add_argument("--replay", type=int, default=600)
    p.add_argument("--lr", type=float, default=3e-6)
    p.add_argument("--extra-train", type=Path)
    p.add_argument("--extra-validation", type=Path)
    p.add_argument("--domain-balanced-selection", action="store_true", help="Select by equal mean NLL across validation sources")
    args = p.parse_args()
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
    train = encode_rows(train_raw + augmented, tokenizer, 300)
    validation_raw = as_training(read_jsonl(args.data / "validation.jsonl"))
    extra_val = as_training(read_jsonl(args.extra_validation)) if args.extra_validation else []
    # Replay validation protects against erasing earlier scam families.
    synthetic_val = [caller_only(r) for r in read_jsonl(DATA / "validation.jsonl") if "caller:" in r["text"].lower()]
    val = encode_rows(validation_raw + synthetic_val + extra_val, tokenizer, 300)
    start = time.monotonic()
    args.output.mkdir(parents=True, exist_ok=True)
    best = float("inf")
    history = []
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=.01)
    print(json.dumps({"device": str(device), "real_training": len(real), "replay": min(args.replay, len(replay)), "augmentation": len(augmented), "extra_training": len(extra_train), "extra_validation": len(extra_val), "validation": len(val)}), flush=True)
    for epoch in range(args.epochs + 1):
        if epoch:
            random.shuffle(train)
            model.train()
            optimizer.zero_grad(set_to_none=True)
            for offset in range(0, len(train), 4):
                inputs, y = batch_tensors(train[offset:offset+4], tokenizer, device)
                logits = model(**inputs).logits[:, :3].float()
                loss = torch.nn.functional.cross_entropy(logits, y) / 4
                loss.backward()
                if (offset // 4 + 1) % 4 == 0 or offset + 4 >= len(train):
                    torch.nn.utils.clip_grad_norm_(model.parameters(), 1)
                    optimizer.step(); optimizer.zero_grad(set_to_none=True)
                if offset % 160 == 0:
                    print(f"epoch {epoch} examples {offset}/{len(train)} loss {loss.item()*4:.4f}", flush=True)
        logits, labels = predict(model, val, tokenizer, device, 8)
        t = temperature_from_validation(logits, labels)
        scores = sigmoid((logits[:, 0] - logits[:, 1]) / t)
        measured = binary_metrics(labels, scores)
        # Equal weight for the distinct validation domains. Hundreds of easy
        # synthetic calls must not drown out a smaller hard-negative sample.
        domains = [measured["nll"]]
        if extra_val:
            hard_metrics = binary_metrics(labels[-len(extra_val):], scores[-len(extra_val):])
            domains += [hard_metrics["nll"]]
        else:
            hard_metrics = None
        source_metrics = {}
        if args.domain_balanced_selection:
            raw_val = validation_raw + synthetic_val + extra_val
            for source in sorted({r["source"] for r in raw_val}):
                indices = [i for i,r in enumerate(raw_val) if r["source"] == source]
                source_metrics[source] = binary_metrics(labels[indices], scores[indices])
            domains = [m["nll"] for m in source_metrics.values()]
        selection_loss = float(np.mean(domains))
        entry = {"epoch": epoch, "temperature": t, "validation": measured,
                 "recorded_validation": binary_metrics(labels[:len(validation_raw)], scores[:len(validation_raw)]),
                 "extra_validation": hard_metrics, "validation_by_source": source_metrics,
                 "selection_loss": selection_loss, "elapsed_sec": time.monotonic() - start}
        history.append(entry)
        print(json.dumps(entry), flush=True)
        if selection_loss < best:
            best = selection_loss
            save_file({k: v.detach().cpu().contiguous() for k,v in model.state_dict().items()}, args.output / "model.safetensors")
            model.config.save_pretrained(args.output)
            tokenizer.save_pretrained(args.output)
            (args.output / "calibration.json").write_text(json.dumps({"temperature": t, "scope": "mixed synthetic and silver recorded-call validation only; not deployment probability calibration", "selected_epoch": epoch}, indent=2)+"\n")
    (args.output / "train_manifest.json").write_text(json.dumps({"base": str(args.model), "seed": seed, "lr": args.lr, "history": history,
        "real_training": len(real), "augmented_training": len(augmented), "extra_training": len(extra_train), "extra_validation": len(extra_val),
        "domain_balanced_selection": args.domain_balanced_selection,
        "extra_training_sources": {s: sum(r["source"] == s for r in extra_train) for s in {r["source"] for r in extra_train}},
        "test_access": "none in training script; second-stage hard cases motivated by exploratory benchmark failures", "deployment": "research candidate only; evaluate before promotion"}, indent=2)+"\n")


if __name__ == "__main__":
    main()
