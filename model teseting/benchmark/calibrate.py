"""Development diagnostic: Platt fit, logit thresholds and per-condition overlap from benchmark windows.

For release calibration use `model teseting/validation/calibrate.py fit`, which requires a frozen,
leakage-checked manifest of independent calibration calls. This tool works directly on `run.py`
output so you can see what calibration can and cannot fix before that data exists.

Phase 3 of the 2026-10-22 audit plan. Input is one or more `per_window.csv` files from
`run.py` (raw float logits per window) plus a label map. Nothing here changes production:
the output `calibration.json` is only used when it is copied next to the checkpoint, and the
agent refuses a file whose checkpoint hash differs, or a development file unless
ALLOW_DEV_CALIBRATION=1.

Label map CSV columns: case,label,source,split
  label  ai | human        source  independent recording group (speaker / call / TTS voice)
  split  dev | heldout     only dev rows are used for fitting; heldout rows are scored once.
`--auto-label-benchmark` builds a map from the benchmark's own case names. Those cases are
reused development clips (3 AI voices, 2 human speakers), so the result is always marked
development and must not be described as a calibrated accuracy.

  python calibrate.py --windows runs/RUN/per_window.csv --auto-label-benchmark \
      --selection candidate_quiet --checkpoint-sha256 <sha> --output runs/RUN/calibration.json
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import defaultdict
from pathlib import Path

import numpy as np

MIN_RELEASE_SOURCES = 8   # per class, independent recordings; a floor, not a sufficiency claim


def auto_label(case):
    """Benchmark case name -> (label, source, condition) or None for mixed/control cases."""
    if case.startswith(("control_", "diagnostic_")) or "_then_" in case:
        return None
    m = re.match(r"(librispeech_test_clean_\d+_40s)(?:__(.+))?$", case)
    if m:
        return "human", m.group(1), m.group(2) or "original"
    m = re.match(r"supplemental_ai_(.+?)__(.+)$", case)
    if m:
        return "ai", m.group(1), m.group(2)
    return "ai", "primary_ai_clip", case


def load(paths, selection, labels):
    rows = []
    for path in paths:
        with open(path, newline="") as source:
            for r in csv.DictReader(source):
                if r["selection"] != selection or r["completed"] != "True":
                    continue
                lab = labels(r["case"])
                if lab is None:
                    continue
                z = float(r["logit"])
                if math.isfinite(z):
                    rows.append(dict(case=r["case"], z=z, w=float(r.get("weight") or 1), **lab))
    return rows


def fit_platt(z, y, w, iters=100, ridge=1e-3):
    """Weighted logistic regression p = sigmoid(a z + b), float64 Newton steps."""
    X = np.stack([z, np.ones_like(z)], 1)
    beta = np.zeros(2)
    for _ in range(iters):
        p = 1 / (1 + np.exp(-np.clip(X @ beta, -50, 50)))
        g = X.T @ (w * (p - y)) + ridge * beta
        H = (X * (w * p * (1 - p))[:, None]).T @ X + ridge * np.eye(2)
        step = np.linalg.solve(H, g)
        beta -= step
        if np.abs(step).max() < 1e-10:
            break
    return float(beta[0]), float(beta[1])


def group_weights(rows):
    """Every independent source contributes equal total weight, then classes are balanced."""
    per_source = defaultdict(float)
    for r in rows:
        per_source[r["source"]] += r["w"]
    w = np.array([r["w"] / per_source[r["source"]] for r in rows])
    y = np.array([r["label"] == "ai" for r in rows], float)
    for cls in (0, 1):
        if (y == cls).any():
            # Each class totals half the window count, so the small ridge stays negligible.
            w[y == cls] *= (len(rows) / 2) / w[y == cls].sum()
    return w, y


def eer_threshold(z, y, w):
    order = np.argsort(z)
    zs, ys, ws = z[order], y[order], w[order]
    fnr = np.cumsum(ws * ys) / (ws * ys).sum()           # AI at or below the cut
    fpr = 1 - np.cumsum(ws * (1 - ys)) / (ws * (1 - ys)).sum()
    i = int(np.argmin(np.abs(fnr - fpr)))
    return float(zs[i]), float((fnr[i] + fpr[i]) / 2)


def fpr_threshold(z, y, w, target):
    hz, hw = z[y == 0], w[y == 0]
    order = np.argsort(hz)[::-1]
    tail = np.cumsum(hw[order]) / hw.sum()
    k = int(np.searchsorted(tail, target, side="right"))
    return float(np.nextafter(hz[order][min(k, len(hz) - 1)], np.inf)) if k < len(hz) else float(hz.min())


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--windows", type=Path, nargs="+", required=True)
    p.add_argument("--labels", type=Path, help="label map CSV (case,label,source,split)")
    p.add_argument("--auto-label-benchmark", action="store_true")
    p.add_argument("--selection", default="current")
    p.add_argument("--checkpoint-sha256", required=True)
    p.add_argument("--target-window-fpr", type=float, default=.01)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--release", action="store_true", help="mark release; refused without enough independent sources")
    a = p.parse_args(argv)
    if a.output.exists():
        raise SystemExit("Refusing to overwrite an existing calibration file")
    if bool(a.labels) == a.auto_label_benchmark:
        raise SystemExit("Pass exactly one of --labels or --auto-label-benchmark")
    if a.labels:
        table = {r["case"]: r for r in csv.DictReader(a.labels.open())}
        labels = lambda c: (dict(label=table[c]["label"], source=table[c]["source"], split=table[c]["split"],
                                 condition=table[c].get("condition", "")) if c in table else None)
    else:
        def labels(c):
            lab = auto_label(c)
            return None if lab is None else dict(label=lab[0], source=lab[1], condition=lab[2], split="dev")
    rows = load(a.windows, a.selection, labels)
    if any(r["label"] not in ("ai", "human") or r["split"] not in ("dev", "heldout") for r in rows):
        raise SystemExit("Labels must be ai|human and splits dev|heldout")
    dev = [r for r in rows if r["split"] == "dev"]
    held = [r for r in rows if r["split"] == "heldout"]
    sources = {cls: sorted({r["source"] for r in dev if r["label"] == cls}) for cls in ("ai", "human")}
    if min(len(v) for v in sources.values()) < 2:
        raise SystemExit(f"Need at least two independent sources per class; got {sources}")
    w, y = group_weights(dev)
    z = np.array([r["z"] for r in dev])
    platt = fit_platt(z, y, w)
    eer_z, eer = eer_threshold(z, y, w)
    fpr_z = fpr_threshold(z, y, w, a.target_window_fpr)
    # Leave-one-source-out: does the fit transfer to a speaker / voice it never saw?
    loso = {}
    for src in sources["ai"] + sources["human"]:
        train = [r for r in dev if r["source"] != src]
        test = [r for r in dev if r["source"] == src]
        tw, ty = group_weights(train)
        aa, bb = fit_platt(np.array([r["z"] for r in train]), ty, tw)
        pt = 1 / (1 + np.exp(-(aa * np.array([r["z"] for r in test]) + bb)))
        loso[src] = dict(label=test[0]["label"], windows=len(test), mean_p_ai=round(float(pt.mean()), 4),
                         wrong_side_fraction=round(float(np.mean(pt >= .5) if test[0]["label"] == "human" else np.mean(pt < .5)), 4))
    by_condition = defaultdict(lambda: {"ai": [], "human": []})
    for r in dev:
        by_condition[r["condition"]][r["label"]].append(r["z"])
    overlap = {c: dict(ai_min=round(min(v["ai"]), 3), human_max=round(max(v["human"]), 3),
                       overlaps=min(v["ai"]) <= max(v["human"]))
               for c, v in sorted(by_condition.items()) if v["ai"] and v["human"]}
    enough = all(len(v) >= MIN_RELEASE_SOURCES for v in sources.values()) and bool(held)
    if a.release and not enough:
        raise SystemExit(f"Release needs >= {MIN_RELEASE_SOURCES} independent sources per class and a held-out split")
    held_report = None
    if held:
        hz = np.array([r["z"] for r in held]); hy = np.array([r["label"] == "ai" for r in held])
        hp = 1 / (1 + np.exp(-(platt[0] * hz + platt[1])))
        held_report = dict(windows=len(held), human_windows_p_ge_0_65=int(np.sum((hp >= .65) & ~hy)),
                           ai_windows_p_le_0_35=int(np.sum((hp <= .35) & hy)),
                           note="window counts; per-call false warnings/misses need the call-level replay")
    out = {"schema": "detector-calibration-v1", "status": "release" if a.release else "development",
           "checkpoint_sha256": a.checkpoint_sha256, "selection": a.selection,
           "platt": {"a": platt[0], "b": platt[1]},
           "logit_threshold_eer": eer_z, "dev_window_eer": round(eer, 4),
           "logit_threshold_window_fpr": {"target": a.target_window_fpr, "logit": fpr_z},
           "sources": sources, "dev_windows": len(dev), "leave_one_source_out": loso,
           "condition_overlap": overlap, "heldout": held_report,
           "inputs": [str(x) for x in a.windows],
           "caveats": ["Windows from one recording are correlated; counts are not independent trials.",
                       "Platt scaling is monotonic: it cannot separate classes whose logits overlap."]}
    a.output.write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps({k: out[k] for k in ("status", "platt", "logit_threshold_eer", "dev_window_eer",
                                           "logit_threshold_window_fpr")}, indent=2))
    print("conditions where AI and human windows overlap:",
          [c for c, v in overlap.items() if v["overlaps"]] or "none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
