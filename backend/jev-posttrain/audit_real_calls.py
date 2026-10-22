"""Fail on exact text, script-group, conversation, or speaker split leakage."""
import argparse
import itertools
import json
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from real_calls import HERE, normalized
from train import read_jsonl


def audit(directory):
    sets = {s: read_jsonl(directory / f"{s}.jsonl") for s in ("train", "validation", "test")}
    report = {"split_counts": {s: len(rows) for s,rows in sets.items()}, "comparisons": {}}
    for s, rows in sets.items():
        if {r["label"] for r in rows} != {0, 1}:
            raise ValueError(f"Both classes required in {s}")
    all_rows = [r for rows in sets.values() for r in rows]
    vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5)).fit([normalized(r["text"]) for r in all_rows])
    for a,b in itertools.combinations(sets, 2):
        left, right = sets[a], sets[b]
        for key, fn in (("text", lambda r: normalized(r["text"])),
                        ("script", lambda r: r["source"] + ":" + r["group"]),
                        ("id", lambda r: r["id"])):
            overlap = set(map(fn,left)) & set(map(fn,right))
            if overlap:
                raise ValueError(f"{key} leakage between {a}/{b}: {len(overlap)}")
        speakers_a = {p for r in left for p in r.get("speakers", [])}
        speakers_b = {p for r in right for p in r.get("speakers", [])}
        if speakers_a & speakers_b:
            raise ValueError("Speaker leakage")
        x = vectorizer.transform([normalized(r["text"]) for r in left])
        y = vectorizer.transform([normalized(r["text"]) for r in right])
        maximum = float((x @ y.T).max())
        report["comparisons"][a+"/"+b] = {"exact_overlaps": 0, "script_overlaps": 0, "speaker_overlaps": 0,
                                                 "max_character_ngram_cosine": maximum}
    report["passed"] = True
    report["limits"] = "Character similarity and source annotations cannot prove semantic independence or gold label correctness."
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--data", type=Path, default=HERE / "data/real_calls")
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    report = audit(args.data)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps(report, indent=2))
