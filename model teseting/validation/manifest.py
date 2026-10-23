"""Validate provenance and partition isolation without reading private audio by default."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

PARTITIONS = {"development", "calibration", "final_test"}


def validate(data: dict, *, verify_audio: bool = False, root: Path | None = None) -> dict:
    errors, owners, identities, ids = [], {}, {}, set()
    sources = data.get("sources", [])
    by_id = {s.get("id"): s for s in sources}
    for source in sources:
        sid = source.get("id")
        if not isinstance(sid, str) or not sid or sid in ids:
            errors.append(f"Missing or duplicate source ID: {sid}")
        ids.add(sid)
        part = source.get("partition")
        if part not in PARTITIONS:
            errors.append(f"{sid}: invalid partition")
        if source.get("label") not in {"human", "ai", "nonspeech", "mixed"}:
            errors.append(f"{sid}: unknown label")
        groups = source.get("groups", [])
        if not groups or any(not isinstance(g, str) or not g for g in groups):
            errors.append(f"{sid}: nonempty leakage groups required")
        keys = [f"group:{g}" for g in groups] + [f"source:{sid}"]
        digest = source.get("sha256")
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            errors.append(f"{sid}: invalid audio sha256")
        else:
            keys.append(f"hash:{digest}")
        for key in keys:
            if key in owners and owners[key] != part:
                errors.append(f"{sid}: partition leakage through {key}")
            owners[key] = part
        for parent in source.get("parents", []):
            if parent not in by_id:
                errors.append(f"{sid}: unknown parent {parent}")
            elif by_id[parent].get("partition") != part:
                errors.append(f"{sid}: parent {parent} is in another partition")
            elif not set(by_id[parent].get("groups", [])).issubset(groups):
                errors.append(f"{sid}: parent {parent} leakage groups not inherited")
        provenance = source.get("provenance", {})
        if not provenance.get("origin") or not provenance.get("rights"):
            errors.append(f"{sid}: origin and rights status required")
        if part in {"calibration", "final_test"}:
            if provenance.get("rights") not in {"licensed", "consented"}:
                errors.append(f"{sid}: unverified evaluation rights")
            if provenance.get("training_overlap") != "verified_disjoint":
                errors.append(f"{sid}: training overlap unresolved")
            if not provenance.get("independent_review"):
                errors.append(f"{sid}: independent provenance review missing")
        if verify_audio:
            p = Path(source.get("path", ""))
            if not p.is_absolute():
                p = (root or Path.cwd()) / p
            if not p.is_file():
                errors.append(f"{sid}: audio missing")
            elif hashlib.file_digest(p.open("rb"), "sha256").hexdigest() != digest:
                errors.append(f"{sid}: audio hash mismatch")
        identities[sid] = set(groups)
    case_ids = set()
    for case in data.get("regression_cases", []):
        cid = case.get("id")
        if cid in case_ids or not cid:
            errors.append(f"Missing or duplicate case ID: {cid}")
        case_ids.add(cid)
        for parent in case.get("sources", []):
            if parent not in by_id:
                errors.append(f"{cid}: unknown original source {parent}")
    return {"valid": not errors, "errors": errors, "source_counts": dict(Counter(s.get("partition") for s in sources)),
            "regression_cases": len(case_ids), "audio_hashes_verified": verify_audio,
            "heldout_ready": any(s.get("partition") == "final_test" for s in sources) and not errors}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("manifest", type=Path)
    p.add_argument("--verify-audio", action="store_true")
    args = p.parse_args()
    result = validate(json.loads(args.manifest.read_text()), verify_audio=args.verify_audio, root=args.manifest.parent.parent)
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
