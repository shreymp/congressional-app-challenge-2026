"""Offline float64 Platt fit, gated on independently partitioned calibration sources.

Outputs a candidate artifact only. Does not modify production thresholds or weights.
Each call has equal weight regardless of window count. No final-test rows allowed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

from manifest import validate


def fit(manifest, rows, checkpoint_sha256):
    import numpy as np
    from scipy.optimize import minimize

    result = validate(manifest)
    if not result["valid"]:
        raise ValueError("Invalid manifest: " + "; ".join(result["errors"]))
    sources = {s["id"]: s for s in manifest["sources"]}
    if not rows:
        raise ValueError("No calibration windows; development regressions cannot substitute")
    if not isinstance(checkpoint_sha256, str) or len(checkpoint_sha256) != 64 or any(c not in "0123456789abcdef" for c in checkpoint_sha256):
        raise ValueError("A verified checkpoint sha256 is required")
    for row in rows:
        source = sources.get(row.get("source_id"), {})
        if source.get("partition") != "calibration":
            raise ValueError("Calibration rows must belong exclusively to registered calibration sources")
        if source.get("label") not in {"human", "ai"}:
            raise ValueError("Mixed/non-speech calls cannot be fitted as one class")
        if not isinstance(row.get("logit"), (int, float)) or not math.isfinite(row["logit"]):
            raise ValueError("Finite raw logits required")
        if row.get("checkpoint_sha256") != checkpoint_sha256:
            raise ValueError("Every score must bind to the same checkpoint")
    registered = {sid for sid, s in sources.items() if s["partition"] == "calibration"}
    included = {r["source_id"] for r in rows}
    if registered != included:
        raise ValueError("All registered calibration calls need outcomes; rejected calls cannot disappear")
    counts = Counter(r["source_id"] for r in rows)
    labels = {sid: sources[sid]["label"] for sid in included}
    if len({s for s in labels.values()}) != 2:
        raise ValueError("Calibration needs both human and AI calls")
    z = np.array([r["logit"] for r in rows], dtype=np.float64)
    y = np.array([labels[r["source_id"]] == "ai" for r in rows], dtype=np.float64)
    weights = np.array([1 / counts[r["source_id"]] for r in rows], dtype=np.float64)
    weights /= weights.sum()
    # Positive slope preserves model ordering; weak ridge prevents unbounded
    # coefficients on a small perfectly separated data set.
    def loss_and_gradient(params):
        a, b = params
        q = a * z + b
        from scipy.special import expit
        delta = weights * (expit(q) - y)
        ridge = 1e-4
        return float(np.sum(weights * (np.logaddexp(0, q) - y * q)) + ridge * (a * a + b * b)), np.array([np.dot(delta, z) + 2 * ridge * a, delta.sum() + 2 * ridge * b])
    solution = minimize(loss_and_gradient, [1., -float(np.dot(weights, z))], method="L-BFGS-B", jac=True,
                        bounds=[(1e-8, 100.), (-1000., 1000.)], options={"ftol": 1e-12, "gtol": 1e-10})
    if not solution.success or not np.all(np.isfinite(solution.x)):
        raise ValueError(f"Calibration did not converge: {solution.message}")
    a, b = map(float, solution.x)
    return {"schema_version": 1, "status": "candidate_requires_frozen_heldout_validation", "method": "float64_call_weighted_platt",
            "a": a, "b": b, "formula": "sigmoid(a * raw_logit + b)", "checkpoint_sha256": checkpoint_sha256,
            "calibration_manifest_sha256": hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            "calls": dict(Counter(labels.values())), "windows": len(rows), "weighting": "each registered call has equal total weight",
            "regularization": 1e-4, "fit_nll_plus_penalty": float(solution.fun),
            "population_calibration_established": False, "production_modified": False}


def threshold_audit(config):
    from math import log, log1p
    values = {}
    for key in ("threshold_eer", "threshold_1pct_fpr"):
        p = float(config[key])
        if not 0 < p < 1:
            raise ValueError("Threshold must lie strictly between zero and one")
        values[key] = {"stored_probability": p, "float64_logit": log(p) - log1p(-p),
                       "float32_steps_below_one": (1 - p) / 2**-24}
    return {"thresholds": values, "inference": "Float32-grid probabilities do not establish the original unsaturated raw-logit operating point.",
            "training_validation_gap": {"validation_eer": config.get("val_eer"), "reported_test": config.get("test")},
            "action": "Recover training notebook/validation logits and audit identities, class balance and source/system splits before changing thresholds.",
            "no_recalibration_performed": True}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="action", required=True)
    audit = sub.add_parser("audit")
    audit.add_argument("config", type=Path)
    calibrate = sub.add_parser("fit")
    calibrate.add_argument("--manifest", required=True, type=Path)
    calibrate.add_argument("--scores", required=True, type=Path)
    calibrate.add_argument("--checkpoint-sha256", required=True)
    calibrate.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    if args.action == "audit":
        print(json.dumps(threshold_audit(json.loads(args.config.read_text())), indent=2, allow_nan=False))
    else:
        result = fit(json.loads(args.manifest.read_text()), json.loads(args.scores.read_text()), args.checkpoint_sha256)
        with args.output.open("x") as handle:
            json.dump(result, handle, indent=2, allow_nan=False)
            handle.write("\n")
        print(json.dumps({"output": str(args.output), "status": result["status"]}))


if __name__ == "__main__":
    main()
