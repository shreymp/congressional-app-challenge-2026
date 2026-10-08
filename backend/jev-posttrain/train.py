"""Locally fine-tune the 151M Jev checkpoint for whole-call scam decisions.

This is an experiment. The resulting checkpoint is not copied into iOS until
held-out quality, calibration, and ONNX/native parity are checked separately.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import time
from collections import Counter
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from gliclass import GLiClassModel
from safetensors.torch import save_file
from transformers import AutoTokenizer

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DATA = HERE / "data" / "prepared"
LABELS = [
    "true: The caller is attempting to scam or defraud the other person.",
    "false: not The caller is attempting to scam or defraud the other person.",
    "insufficient evidence",
]
PROPOSITION = "The caller is attempting to scam or defraud the other person."


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def balanced_sample(rows: list[dict], per_source: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    groups: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        groups.setdefault((r["source"], r["target_id"]), []).append(r)
    result = []
    for group in groups.values():
        rng.shuffle(group)
        result.extend(group[: per_source // 2])
    rng.shuffle(result)
    return result


def prepare_prompt(r: dict, tokenizer, max_context_tokens: int) -> str:
    text = r["text"].split("Context:\n", 1)[1].rsplit("\n\nEvaluate proposition:", 1)[0]
    token_ids = tokenizer(text, add_special_tokens=False)["input_ids"]
    if len(token_ids) > max_context_tokens:
        text = tokenizer.decode(token_ids[-max_context_tokens:], skip_special_tokens=True)
    prefix = "".join(f"<<LABEL>>{label}" for label in LABELS)
    return f"{prefix}<<SEP>>Context:\n{text}\n\nEvaluate proposition: {PROPOSITION}"


def caller_only(r: dict) -> dict:
    """Keep only utterances tagged as caller; preserve the call's original label."""
    raw = r["text"].split("Context:\n", 1)[1].rsplit("\n\nEvaluate proposition:", 1)[0]
    turns = re.findall(r"caller:\s*(.*?)(?=\s*(?:receiver:|caller:)|$)", raw, re.I | re.S)
    if not turns:
        raise ValueError("No caller turns found; cannot create caller-only example")
    copy = dict(r)
    copy["text"] = f"Context:\nCaller: {' '.join(t.strip() for t in turns)}\n\nEvaluate proposition: {PROPOSITION}"
    return copy


def encode_rows(rows: list[dict], tokenizer, max_context_tokens: int) -> list[dict]:
    result = []
    for r in rows:
        prompt = prepare_prompt(r, tokenizer, max_context_tokens)
        ids = tokenizer(prompt, truncation=False)["input_ids"]
        if len(ids) > 512:
            raise ValueError(f"Prompt exceeds 512 tokens: {len(ids)}")
        result.append({"ids": ids, "target": 0 if r["target_id"] == "true" else 1, "source": r["source"], "sha256": r["text_sha256"]})
    return result


def batch_tensors(rows: list[dict], tokenizer, device: torch.device) -> tuple[dict, torch.Tensor]:
    enc = tokenizer.pad({"input_ids": [r["ids"] for r in rows]}, padding=True, return_tensors="pt")
    inputs = {k: v.to(device) for k, v in enc.items() if k in ("input_ids", "attention_mask")}
    labels = torch.tensor([r["target"] for r in rows], dtype=torch.long, device=device)
    return inputs, labels


@torch.no_grad()
def predict(model, rows: list[dict], tokenizer, device, batch_size: int) -> tuple[np.ndarray, np.ndarray]:
    model.eval()
    logits, labels = [], []
    for offset in range(0, len(rows), batch_size):
        batch = rows[offset:offset + batch_size]
        inputs, y = batch_tensors(batch, tokenizer, device)
        logits.append(model(**inputs).logits[:, :3].float().cpu().numpy())
        labels.append(y.cpu().numpy())
    return np.concatenate(logits), np.concatenate(labels)


def metrics(logits: np.ndarray, labels: np.ndarray) -> dict[str, float]:
    z = logits - logits.max(axis=1, keepdims=True)
    probs = np.exp(z) / np.exp(z).sum(axis=1, keepdims=True)
    pred = probs.argmax(axis=1)
    return {
        "accuracy": float((pred == labels).mean()),
        "nll": float(-np.log(np.clip(probs[np.arange(len(labels)), labels], 1e-9, 1)).mean()),
        "brier": float(np.square(probs - np.eye(3)[labels]).sum(axis=1).mean()),
        "mean_abstain_probability": float(probs[:, 2].mean()),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--model", type=Path, default=ROOT / "verdict-151m")
    p.add_argument("--output", type=Path, default=HERE / "runs" / "call-v1")
    p.add_argument("--per-source", type=int, default=600)
    p.add_argument("--epochs", type=int, default=2)
    p.add_argument("--batch-size", type=int, default=4)
    p.add_argument("--grad-accum", type=int, default=4)
    p.add_argument("--max-context-tokens", type=int, default=300)
    p.add_argument("--seed", type=int, default=20261008)
    p.add_argument("--caller-only", action="store_true", help="Train and validate on caller-only versions of source calls")
    p.add_argument("--lr", type=float, default=2e-5)
    args = p.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    args.output.mkdir(parents=True, exist_ok=True)
    print(f"Device: {device}; model: {args.model}; output: {args.output}", flush=True)
    tokenizer = AutoTokenizer.from_pretrained(args.model)
    model = GLiClassModel.from_pretrained(args.model).to(device)
    train_raw = balanced_sample(read_jsonl(DATA / "train.jsonl"), args.per_source, args.seed)
    val_raw = read_jsonl(DATA / "validation.jsonl")
    if args.caller_only:
        before = len(train_raw)
        train_raw = [caller_only(r) for r in train_raw if re.search(r"\bcaller:", r["text"], re.I)]
        val_raw = [caller_only(r) for r in val_raw if re.search(r"\bcaller:", r["text"], re.I)]
        print(f"Skipped {before - len(train_raw)} training calls without an explicit caller tag", flush=True)
    train = encode_rows(train_raw, tokenizer, args.max_context_tokens)
    val = encode_rows(val_raw, tokenizer, args.max_context_tokens)
    print(f"Train: {len(train)} {dict(Counter(r['source'] for r in train))}; validation: {len(val)}", flush=True)
    print(f"Max prompt length: {max(len(r['ids']) for r in train + val)}", flush=True)
    base_logits, base_labels = predict(model, val, tokenizer, device, args.batch_size * 2)
    baseline = metrics(base_logits, base_labels)
    print(f"Baseline validation: {json.dumps(baseline)}", flush=True)

    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    total_steps = args.epochs * ((len(train) + args.batch_size - 1) // args.batch_size)
    total_updates = max(1, (total_steps + args.grad_accum - 1) // args.grad_accum)
    from transformers import get_cosine_schedule_with_warmup
    scheduler = get_cosine_schedule_with_warmup(optimizer, max(1, total_updates // 10), total_updates)
    best_nll = baseline["nll"]
    history = [{"epoch": 0, "validation": baseline}]
    start = time.monotonic()
    micro_step = 0
    for epoch in range(1, args.epochs + 1):
        random.shuffle(train)
        model.train()
        optimizer.zero_grad(set_to_none=True)
        running_loss = 0.0
        for offset in range(0, len(train), args.batch_size):
            batch = train[offset:offset + args.batch_size]
            inputs, labels = batch_tensors(batch, tokenizer, device)
            logits = model(**inputs).logits[:, :3].float()
            ce = F.cross_entropy(logits, labels)
            brier = torch.square(F.softmax(logits, dim=-1) - F.one_hot(labels, 3)).sum(dim=-1).mean()
            loss = ce + brier
            (loss / args.grad_accum).backward()
            running_loss += float(loss.detach().cpu())
            micro_step += 1
            if micro_step % args.grad_accum == 0 or offset + args.batch_size >= len(train):
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
                scheduler.step()
                optimizer.zero_grad(set_to_none=True)
            if micro_step % 25 == 0:
                print(f"Epoch {epoch} step {micro_step}/{total_steps}; loss {running_loss / (offset // args.batch_size + 1):.4f}; elapsed {time.monotonic() - start:.0f}s", flush=True)
        val_logits, val_labels = predict(model, val, tokenizer, device, args.batch_size * 2)
        result = metrics(val_logits, val_labels)
        print(f"Epoch {epoch} validation: {json.dumps(result)}", flush=True)
        history.append({"epoch": epoch, "validation": result, "mean_loss": running_loss / max(1, len(train) / args.batch_size)})
        if result["nll"] < best_nll:
            best_nll = result["nll"]
            save_file({k: v.detach().cpu().contiguous() for k, v in model.state_dict().items()}, str(args.output / "model.safetensors"))
            tokenizer.save_pretrained(args.output)
            model.config.save_pretrained(args.output)
            print(f"Saved best checkpoint (epoch {epoch})", flush=True)
        (args.output / "train_manifest.json").write_text(json.dumps({
            "base_model": str(args.model), "seed": args.seed, "train_count": len(train),
            "validation_count": len(val), "batch_size": args.batch_size,
            "gradient_accumulation": args.grad_accum, "epochs": args.epochs,
            "max_context_tokens": args.max_context_tokens,
            "optimizer": "AdamW", "learning_rate": args.lr, "loss": "cross_entropy + Brier",
            "caller_only": args.caller_only,
            "selection": "validation NLL", "best_validation_nll": best_nll,
            "device": str(device), "elapsed_seconds": time.monotonic() - start,
            "history": history,
        }, indent=2) + "\n")


if __name__ == "__main__":
    main()
