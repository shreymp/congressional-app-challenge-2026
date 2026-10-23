"""Build training/validation prefixes from their own benign calls only.

No test data is read. These are partial transcripts of existing recordings,
not additional independent calls or independently labeled streaming examples.
Fraud-call prefixes are excluded: their whole-call label may not apply yet.
"""
import hashlib
import json
from pathlib import Path

from real_calls import normalized

HERE = Path(__file__).resolve().parent


def prefixes(rows):
    result, seen = [], set()
    for row in rows:
        if row["label"] != 0:
            continue
        words = row["text"].split()
        for fraction in (1 / 3, 2 / 3):
            count = int(len(words) * fraction)
            if count < 20:
                continue
            text = " ".join(words[:count])
            key = normalized(text)
            if key in seen:
                continue
            seen.add(key)
            result.append({**row, "id": f"{row['id']}:prefix:{count}",
                           "parent_id": row["id"], "text": text,
                           "source": row["source"] + "_prefix",
                           "label_quality": "inherited_benign_context_not_prefix_adjudicated"})
    return result


def build(data, output):
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    prepared, inputs = {}, {}
    for split in ("train", "validation"):
        paths = [data / f"{split}.jsonl", data / "banking_training" / f"{split}.jsonl"]
        sets = []
        for path in paths:
            inputs[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
            sets.append([json.loads(line) for line in path.read_text().splitlines() if line])
        # Existing bank and authored replay is preserved. Only recorded/natural
        # benign rows supply prefixes; authored contrasts remain separate.
        recorded = [r for rows in sets for r in rows if r["source"] != "authored_paired_training"]
        prepared[split] = sets[1] + prefixes(recorded)
    left = {normalized(r["text"]) for r in prepared["train"]}
    right = {normalized(r["text"]) for r in prepared["validation"]}
    if left & right:
        raise ValueError("Exact prefix text crosses training/validation")
    train_parents = {r.get("parent_id", r["id"]) for r in prepared["train"]}
    validation_parents = {r.get("parent_id", r["id"]) for r in prepared["validation"]}
    if train_parents & validation_parents:
        raise ValueError("Parent call crosses training/validation")
    output.mkdir(parents=True)
    for split, rows in prepared.items():
        (output / f"{split}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    report = {"input_sha256": inputs, "counts": {s: len(r) for s, r in prepared.items()},
              "test_access": "none", "parent_overlap": 0, "exact_text_overlap": 0,
              "limits": "Prefixes inherit imperfect benign labels; no new independent calls. Banking speakers/scenarios can overlap. Existing tests are exploratory."}
    (output / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    print(json.dumps(build(HERE / "data/real_calls", HERE / "data/real_calls/benign_prefix_training"), indent=2))
