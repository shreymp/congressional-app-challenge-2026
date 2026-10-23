"""Call-level weighting, split auditing and fail-closed checkpoint selection.

Labels here use the training convention: true/0 is scam, false/1 is normal.
No model or test files are loaded by this module.
"""
from collections import Counter, defaultdict
import hashlib
import json
import math
import re


def domain(row):
    source = row.get("validation_domain", row["source"])
    # Prefixes of a domain are not independent validation domains.
    return re.sub(r"(?:_prefix)+$", "", source)


def parent(row):
    identity = row.get("parent_id") or row.get("id") or row.get("text_sha256")
    if not identity:
        raise ValueError("Every training presentation needs a parent identity")
    return domain(row), str(identity)


def balanced_parent_weights(rows):
    """Half the objective per class; each parent shares its mass among variants."""
    counts = Counter(parent(r) for r in rows)
    targets = {}
    for row in rows:
        key, target = parent(row), row["target_id"]
        if target not in ("true", "false"):
            raise ValueError("Binary weighting requires explicit true/false labels")
        if key in targets and targets[key] != target:
            raise ValueError("Conflicting labels for one parent call")
        targets[key] = target
    classes = Counter(targets.values())
    if set(classes) != {"true", "false"}:
        raise ValueError("Both classes are required")
    weights = [len(rows) / (2 * classes[r["target_id"]] * counts[parent(r)]) for r in rows]
    return weights, {"presentations": len(rows), "parents": len(targets),
                     "parent_classes": dict(classes), "effective_class_share": {"true": .5, "false": .5}}


def _fingerprint(text):
    text = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", text.lower())).strip()
    return hashlib.sha256(text.encode()).hexdigest()


def audit_splits(train, validation):
    """Reject parent, script-group, speaker or exact-text train/validation leaks."""
    def identities(rows, kind):
        if kind == "parent":
            return {parent(r) for r in rows}
        if kind == "text":
            return {_fingerprint(r["text"]) for r in rows}
        if kind == "group":
            return {(domain(r), str(r["group"])) for r in rows if r.get("group")}
        return {(domain(r), str(s)) for r in rows for s in r.get("speakers", [])}
    counts = {}
    for kind in ("parent", "group", "speaker", "text"):
        overlap = identities(train, kind) & identities(validation, kind)
        counts[kind] = len(overlap)
        if overlap:
            raise ValueError(f"Training/validation {kind} overlap: {len(overlap)}")
    return counts


def confusion(rows, scores, threshold):
    if not rows or len(rows) != len(scores) or not math.isfinite(threshold):
        raise ValueError("Nonempty, aligned scores required")
    if any(not math.isfinite(float(p)) or not 0 <= p <= 1 for p in scores):
        raise ValueError("Invalid scores")
    labels = [r.get("target_id") == "true" if "target_id" in r else r["label"] == 1 for r in rows]
    tp = int(sum(y and p >= threshold for y, p in zip(labels, scores)))
    fn = int(sum(y and p < threshold for y, p in zip(labels, scores)))
    fp = int(sum(not y and p >= threshold for y, p in zip(labels, scores)))
    tn = len(rows) - tp - fn - fp
    return {"n": len(rows), "tp": tp, "tn": tn, "fp": fp, "fn": fn,
            "accuracy": (tp + tn) / len(rows), "recall": tp / (tp + fn) if tp + fn else None,
            "false_positive_rate": fp / (fp + tn) if fp + tn else None}


def regression_gate(rows, baseline, candidate, thresholds=(.5, .75)):
    """No additional missed scams OR false alerts, overall and per parent domain.

    The same fixed score scale and cutoff must be supplied for both checkpoints.
    This is a validation gate, not a claim about future calls.
    """
    if len(baseline) != len(rows) or len(candidate) != len(rows):
        raise ValueError("Missing validation scores")
    confusion(rows, baseline, .5)
    confusion(rows, candidate, .5)
    # A call and its prefixes count once: an alert on any variant is an alert.
    members = defaultdict(list)
    for i, row in enumerate(rows):
        members[parent(row)].append(i)
    original_rows = rows
    rows = [original_rows[idx[0]] for idx in members.values()]
    baseline = [max(baseline[i] for i in idx) for idx in members.values()]
    candidate = [max(candidate[i] for i in idx) for idx in members.values()]
    groups = {"all": list(range(len(rows)))}
    for source in sorted({domain(r) for r in rows}):
        groups["source:" + source] = [i for i, r in enumerate(rows) if domain(r) == source]
    failures, details = [], {}
    for name, indices in groups.items():
        selected = [rows[i] for i in indices]
        for threshold in thresholds:
            key = f"{name}@{threshold}"
            before = confusion(selected, [baseline[i] for i in indices], threshold)
            after = confusion(selected, [candidate[i] for i in indices], threshold)
            details[key] = {"baseline": before, "candidate": after}
            for error in ("fn", "fp"):
                if after[error] > before[error]:
                    failures.append(f"{key}: {error} increased {before[error]} -> {after[error]}")
    return {"passed": not failures, "failures": failures, "groups": details}


def parent_domain_nll(rows, scores):
    """Average variants within a call, then calls within their original domain."""
    confusion(rows, scores, .5)  # Reject incomplete/nonfinite inference results.
    groups = defaultdict(lambda: defaultdict(list))
    for row, score in zip(rows, scores):
        y = row["target_id"] == "true"
        p = min(1 - 1e-8, max(1e-8, float(score)))
        groups[domain(row)][parent(row)].append(-math.log(p if y else 1 - p))
    return sum(sum(sum(v) / len(v) for v in calls.values()) / len(calls)
               for calls in groups.values()) / len(groups)


def fit_operating_point(rows, scores, *, min_recall=.90, max_fpr=.05):
    """Validation-only fit with a false-alert bound in EVERY benign domain.

    A failed fit has no threshold. Callers must not silently fall back to a
    test-selected cutoff or call a failed result a usable warning policy.
    """
    if not 0 < min_recall <= 1 or not 0 <= max_fpr < 1:
        raise ValueError("Invalid operating requirements")
    confusion(rows, scores, .5)
    if any(r["label"] not in (0, 1) for r in rows):
        raise ValueError("Cutoff validation needs explicit binary labels")
    if not any(r["label"] == 1 for r in rows) or not any(r["label"] == 0 for r in rows):
        raise ValueError("Calibration requires scams and normal conversations")
    groups = {s: [i for i, r in enumerate(rows) if domain(r) == s and r["label"] == 0]
              for s in {domain(r) for r in rows}}
    feasible, affordable_recall, required_worst_fpr = [], 0.0, 1.0
    for cutoff in sorted({0.0, 1.0, *map(float, scores)}):
        metric = confusion(rows, scores, cutoff)
        worst_fpr = max(confusion([rows[i] for i in idx], [scores[i] for i in idx], cutoff)["false_positive_rate"]
                        for idx in groups.values() if idx)
        if worst_fpr <= max_fpr:
            affordable_recall = max(affordable_recall, metric["recall"])
        if metric["recall"] >= min_recall:
            required_worst_fpr = min(required_worst_fpr, worst_fpr)
        if metric["recall"] < min_recall or worst_fpr > max_fpr:
            continue
        feasible.append((metric["accuracy"], metric["recall"], -metric["fp"], cutoff, metric))
    if not feasible:
        return {"passed": False, "threshold": None,
                "reason": "No validation cutoff meets recall and per-domain false-alert requirements",
                "maximum_recall_within_false_alert_budgets": affordable_recall,
                "minimum_worst_domain_fpr_for_required_recall": required_worst_fpr,
                "min_recall": min_recall, "max_fpr_each_benign_domain": max_fpr}
    *_, cutoff, metric = max(feasible)
    return {"passed": True, "threshold": cutoff, "validation": metric,
            "min_recall": min_recall, "max_fpr_each_benign_domain": max_fpr,
            "scope": "validation operating point; score is not a field scam probability"}


def validate_decision_policy(policy, directory):
    """A failed, corrupted or mismatched research policy never yields a verdict."""
    if policy.get("passed") is not True:
        raise ValueError("Policy failed validation; no usable warning cutoff exists")
    threshold, temperature = policy.get("threshold"), policy.get("temperature")
    if (type(threshold) not in (int, float) or not math.isfinite(threshold) or not 0 <= threshold <= 1
            or type(temperature) not in (int, float) or not math.isfinite(temperature) or temperature <= 0):
        raise ValueError("Invalid policy threshold/temperature")
    if policy.get("context_mode") != "windows" or policy.get("research_only") is not True:
        raise ValueError("Unsupported decision policy scope or inference mode")
    for name, key in (("model.safetensors", "checkpoint_sha256"), ("tokenizer.json", "tokenizer_sha256")):
        with (directory / name).open("rb") as source:
            actual = hashlib.file_digest(source, "sha256").hexdigest()
        if actual != policy.get(key):
            raise ValueError(f"Decision policy does not match {name}")
    if json.loads((directory / "calibration.json").read_text())["temperature"] != temperature:
        raise ValueError("Policy temperature does not match checkpoint calibration")
