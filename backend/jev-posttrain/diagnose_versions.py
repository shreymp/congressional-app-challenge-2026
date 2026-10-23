"""Read-only model diagnosis on the already-inspected human100 sample.

Threshold sweeps here are explicitly post-hoc diagnostics, never deployable
threshold selection or evidence of independent 90% performance.
"""
import csv
import json
from pathlib import Path

import numpy as np
import torch
from gliclass import GLiClassModel
from sklearn.metrics import roc_auc_score, average_precision_score
from transformers import AutoTokenizer

from benchmark_real import infer, summarize
from train import read_jsonl, caller_only, DATA

HERE = Path(__file__).resolve().parent
OUT = HERE.parents[1] / "docs/testing/2026-10-22-jev-diagnosis"


def rank_stats(rows, ps):
    y = np.array([r["label"] for r in rows])
    ps = np.array(ps)
    thresholds = np.r_[0, np.unique(ps), 1]
    correct = [int(((ps >= t) == y).sum()) for t in thresholds]
    index = int(np.argmax(correct))
    return {"roc_auc": float(roc_auc_score(y, ps)), "average_precision": float(average_precision_score(y, ps)),
        "scam_score_quantiles": np.quantile(ps[y == 1], [0, .25, .5, .75, 1]).tolist(),
        "normal_score_quantiles": np.quantile(ps[y == 0], [0, .25, .5, .75, 1]).tolist(),
        "posthoc_test_oracle": {"correct": correct[index], "n": len(rows), "threshold": float(thresholds[index]),
          "warning": "Chosen with test answers. Diagnostic upper bound for a single cutoff on these scores only; not validated accuracy, not a deployment threshold."}}


def main():
    if OUT.exists():
        raise FileExistsError(OUT)
    rows = read_jsonl(HERE / "data/real_calls/human100/test.jsonl")
    prior = list(csv.DictReader((HERE.parents[1] / "docs/testing/2026-10-22-human100/100-tests.csv").open()))
    lookup = {r["id"]: r for r in prior}
    stats = {m: rank_stats(rows, [float(lookup[r["id"]][m + "_score"]) for r in rows]) for m in ("v2", "v5", "v6")}
    y = np.array([r["label"] for r in rows])
    a = np.array([float(lookup[r["id"]]["v5_score"]) for r in rows])
    b = np.array([float(lookup[r["id"]]["v6_score"]) for r in rows])
    report = {"ranking": stats, "v6_vs_v5_score_decreases": {"scam": int(((b < a) & (y == 1)).sum()),
        "normal": int(((b < a) & (y == 0)).sum())}, "training": {}, "ablations": {}}
    # Reconstruct the same replay class composition using the saved seed.
    import random
    replay = [caller_only(r) for r in read_jsonl(DATA / "train.jsonl") if "caller:" in r["text"].lower()]
    random.Random(20261020).shuffle(replay)
    replay = replay[:600]
    real = read_jsonl(HERE / "data/real_calls/train.jsonl")
    for version, extra in (("v5", "banking_training"), ("v6", "benign_prefix_training")):
        more = read_jsonl(HERE / "data/real_calls" / extra / "train.jsonl")
        positive = 2 * sum(r["label"] == 1 for r in real) + sum(r["target_id"] == "true" for r in replay) + sum(r["label"] == 1 for r in more)
        total = 2 * len(real) + len(replay) + len(more)
        directory = HERE / "runs" / ("call-v5-balanced" if version == "v5" else "call-v6-prefix")
        manifest = json.loads((directory / "train_manifest.json").read_text())
        final = manifest["history"][-1]
        report["training"][version] = {"total": total, "positive": positive, "negative": total - positive,
            "normal_share": (total - positive) / total, "validation_selection_sources": final["validation_by_source"],
            "selection_loss_before_after": [r["selection_loss"] for r in manifest["history"]]}
    torch.set_num_threads(4)
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    for version, path in (("v3", "call-v3-real"), ("v5", "call-v5-balanced"), ("v6", "call-v6-prefix")):
        directory = HERE / "runs" / path
        tokenizer = AutoTokenizer.from_pretrained(directory, local_files_only=True)
        model = GLiClassModel.from_pretrained(directory, local_files_only=True).to(device)
        temperature = json.loads((directory / "calibration.json").read_text())["temperature"]
        if version == "v3":
            ps = infer(model, tokenizer, rows, device, temperature, "windows")
            report["ranking"][version] = rank_stats(rows, ps)
            report["v3_same_100"] = summarize(rows, ps)
        variants = {}
        if version in ("v5", "v6"):
            for name in ("caller_prefix", "no_prefix"):
                altered = [{**r, "text": ("Caller: " if name == "caller_prefix" else "") + r["text"].removeprefix("Conversation: ")} for r in rows]
                ps = infer(model, tokenizer, altered, device, temperature, "windows")
                variants[name] = summarize(altered, ps)
            lengths = [len(tokenizer(r["text"], add_special_tokens=False)["input_ids"]) for r in rows]
            variants["context"] = {"n_over_300_tokens": sum(n > 300 for n in lengths), "max_tokens": max(lengths)}
        report["ablations"][version] = variants
        del model
        if device.type == "mps": torch.mps.empty_cache()
    report["limits"] = "All test-derived thresholds and ablations are exploratory. Labels remain source-attributed, not adjudicated for excerpt sufficiency. No model training or deployment change."
    OUT.mkdir(parents=True)
    (OUT / "diagnostics.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"ranking": report["ranking"], "v6_vs_v5_score_decreases": report["v6_vs_v5_score_decreases"], "v3_same_100": report["v3_same_100"], "ablations": report["ablations"]}, indent=2))


if __name__ == "__main__":
    main()
