"""Fail closed on independent call metrics, unresolved outcomes, and actual-device checks."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from manifest import validate


def upper_bound(failures: int, total: int, confidence: float) -> float | None:
    if total == 0:
        return None
    if failures == total:
        return 1.0
    from scipy.stats import beta
    return float(beta.ppf(confidence, failures + 1, total - failures))


def percentile(values, q):
    if not values:
        return None
    s = sorted(values)
    return s[max(0, math.ceil(q * len(s)) - 1)]


def evaluate(manifest: dict, spec: dict, outcomes: dict) -> dict:
    problems = []
    report = validate(manifest)
    problems.extend(report["errors"])
    sources = {s["id"]: s for s in manifest.get("sources", [])}
    required = {s["id"] for s in sources.values() if s["partition"] == "final_test"}
    if not required:
        problems.append("No independent final-test sources registered")
    seen, groups, human, ai, uncovered, detected, recovered = set(), set(), [], [], [], [], []
    supplied_rows = outcomes.get("calls", [])
    reported_ids = {row.get("source_id") for row in supplied_rows} & required
    missing_ids = required - reported_ids
    for sid in sorted(missing_ids):
        problems.append(f"Missing final-test call: {sid}")
    # Register unknown failure rows so missing calls remain in every denominator.
    for row in [*supplied_rows, *({"source_id": sid} for sid in sorted(missing_ids))]:
        sid = row.get("source_id")
        if sid not in required or sid in seen:
            problems.append(f"Unregistered or duplicate final-test unit: {sid}")
            continue
        seen.add(sid)
        source = sources[sid]
        keys = set(source["groups"])
        if groups & keys:
            problems.append(f"Dependent final-test unit {sid}; use a preregistered cluster analysis")
        groups.update(keys)
        missing = [k for k in ("human_false_headline", "human_false_warning", "ai_missed", "ai_deadline_missed", "analysis_uncovered")
                   if not isinstance(row.get(k), bool)]
        if missing:
            problems.append(f"{sid}: unknown outcomes: {', '.join(missing)}")
        # Unknown outcomes count as failures; never drop unscored or rejected calls.
        uncovered.append(row.get("analysis_uncovered") is not False)
        if source["label"] in {"human", "mixed"}:
            human.append(row.get("human_false_headline") is not False or row.get("human_false_warning") is not False)
        if source["label"] in {"ai", "mixed"}:
            ai.append((row.get("ai_missed") is not False, row.get("ai_deadline_missed") is not False))
        overlap = row.get("human_with_fresh_warning_sec")
        if not isinstance(overlap, (int, float)) or not math.isfinite(overlap) or overlap < 0 or overlap > spec["max_human_with_fresh_warning_sec"]:
            problems.append(f"{sid}: Human headline/fresh warning overlap missing or above budget")
        # Every registered transition must have an outcome, including failures.
        expected = source.get("transitions", [])
        measured = row.get("transitions", [])
        if len(expected) != len(measured):
            problems.append(f"{sid}: transition outcomes missing")
        for index, transition in enumerate(expected):
            result = measured[index] if index < len(measured) else {}
            delay = result.get("delay_sec")
            if result.get("target") != transition["target"] or not isinstance(delay, (int, float)) or not math.isfinite(delay) or delay < 0:
                problems.append(f"{sid}: transition {index} unresolved")
                continue
            (detected if transition["target"] == "ai" else recovered).append(delay)
    coverage_fields = {"human_speakers": "human_speaker_id", "synthetic_voices": "synthetic_voice_id",
                       "synthetic_systems": "synthetic_system_id"}
    coverage = {}
    for goal, field in coverage_fields.items():
        coverage[goal] = len({sources[sid].get(field) for sid in required if sources[sid].get(field)})
        if coverage[goal] < spec["coverage_milestone"][goal]:
            problems.append(f"Coverage milestone unmet: {goal}")
    counts = {"human_false_warning": (sum(human), len(human)), "ai_missed": (sum(a[0] for a in ai), len(ai)),
              "ai_deadline_missed": (sum(a[1] for a in ai), len(ai)), "analysis_uncovered": (sum(uncovered), len(uncovered))}
    rates = {}
    for metric, (failures, total) in counts.items():
        bound = upper_bound(failures, total, spec["confidence"])
        rates[metric] = {"failures": failures, "independent_units": total, "upper_bound": bound,
                         "budget": spec["max_failure_upper_bound"][metric]}
        if bound is None or bound > spec["max_failure_upper_bound"][metric]:
            problems.append(f"{metric}: insufficient evidence or failure bound above budget")
    for metric, values, budget in [("switch_detection_p95_sec", detected, spec["max_switch_detection_p95_sec"]),
                                   ("human_recovery_p95_sec", recovered, spec["max_human_recovery_p95_sec"])]:
        value = percentile(values, .95)
        if value is None or value > budget:
            problems.append(f"{metric}: missing or above budget")
        rates[metric] = {"value": value, "transitions": len(values), "budget": budget}
    for check in spec["required_checks"]:
        entry = outcomes.get("checks", {}).get(check, {})
        if entry.get("status") != "passed" or not entry.get("artifact"):
            problems.append(f"Required executed check missing: {check}")
        else:
            artifact = Path(entry["artifact"])
            if not artifact.is_file() or entry.get("sha256") != hashlib.file_digest(artifact.open("rb"), "sha256").hexdigest():
                problems.append(f"Executed check artifact absent or hash mismatch: {check}")
    binding = outcomes.get("frozen_bundle", {})
    for name in ("checkpoint_sha256", "architecture_sha256", "policy_sha256", "manifest_sha256", "release_spec_sha256", "source_sha256"):
        value = binding.get(name, "")
        if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            problems.append(f"Frozen bundle hash missing: {name}")
    canonical = lambda value: hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    for key, value in (("manifest_sha256", manifest), ("release_spec_sha256", spec)):
        if binding.get(key) != canonical(value):
            problems.append(f"Frozen bundle does not match {key}")
    return {"release_allowed": not problems, "blocking_reasons": problems, "metrics": rates,
            "registered_final_test_sources": len(required), "reported_final_test_sources": len(reported_ids), "coverage": coverage,
            "statistical_unit": "registered independent source/speaker group, never a window or transformed clip"}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    here = Path(__file__).resolve().parent
    p.add_argument("--manifest", type=Path, default=here / "data_manifest.json")
    p.add_argument("--spec", type=Path, default=here / "release_spec.json")
    p.add_argument("--outcomes", type=Path, default=here / "release_outcomes.json")
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    result = evaluate(*(json.loads(f.read_text()) for f in (args.manifest, args.spec, args.outcomes)))
    text = json.dumps(result, indent=2, allow_nan=False) + "\n"
    if args.output:
        with args.output.open("x") as handle:
            handle.write(text)
    print(text, end="")
    return 0 if result["release_allowed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
