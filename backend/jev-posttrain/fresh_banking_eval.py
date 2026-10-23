"""Freeze new call-disjoint roleplay probes before scoring V5/V6.

This is a new call sample from an already-used source, NOT a source-independent
real-world benchmark. Never use these calls for training or model selection.
"""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path

from fetch_public_eval import BASE, fetch
from real_calls import normalized

HERE = Path(__file__).resolve().parent


def freeze(tree, output, count):
    if output.exists():
        raise FileExistsError(output)
    data = HERE / "data/real_calls"
    old_paths = [data / "hvb/probes.jsonl"] + [data / "banking_training" / f"{s}.jsonl" for s in ("train", "validation")]
    used = [json.loads(line) for p in old_paths for line in p.read_text().splitlines() if line]
    excluded = {r["id"] for r in used}
    seen = {normalized(r["text"]) for r in used}
    paths = [r["path"] for r in json.loads(tree.read_text())["tree"] if r["path"].startswith("data/transcript/") and r["path"].endswith(".json")]
    paths.sort(key=lambda p: hashlib.sha256(("fresh-eval-20261022:" + p).encode()).hexdigest())
    paths = [p for p in paths if "hvb:" + Path(p).stem not in excluded]

    def one(path):
        content = fetch(BASE + path)
        turns = json.loads(content)
        return {"id": "hvb:" + Path(path).stem, "label": 0, "source": "fresh_hvb_roleplay",
                "text": "Caller: " + " ".join(t["human_transcript"] for t in turns if t["speaker_role"] == "agent"),
                "url": BASE + path, "sha256": hashlib.sha256(content).hexdigest()}

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        candidates = list(pool.map(one, paths[:count + 30]))
    rows = []
    for r in candidates:
        key = normalized(r["text"])
        if key in seen or len(key.split()) < 20:
            continue
        seen.add(key)
        rows.append(r)
        if len(rows) == count:
            break
    if len(rows) != count:
        raise ValueError("Not enough distinct calls")
    output.mkdir(parents=True)
    payload = "".join(json.dumps(r) + "\n" for r in rows)
    (output / "probes.jsonl").write_text(payload)
    manifest = {"count": count, "sha256": hashlib.sha256(payload.encode()).hexdigest(),
                "thresholds": [0.5, 0.75], "training_use": "forbidden for this experiment",
                "baseline_sha256": hashlib.sha256((HERE / "runs/call-v5-balanced/model.safetensors").read_bytes()).hexdigest(),
                "source": "https://github.com/cricketclub/gridspace-stanford-harper-valley", "license": "CC BY 4.0",
                "limits": "Benign recorded roleplay only. Calls/exact text disjoint from prior probes and training. Speakers/scenarios may overlap. Cannot measure scam recall or organic real-world accuracy."}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--tree", type=Path, required=True)
    p.add_argument("--count", type=int, default=100)
    p.add_argument("--output", type=Path, default=HERE / "data/real_calls/fresh_banking_20261022")
    args = p.parse_args()
    print(json.dumps(freeze(args.tree, args.output, args.count), indent=2))
