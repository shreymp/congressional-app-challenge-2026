"""Separate banking-roleplay development data for the final training pass.

Never trains on the 40 previously inspected external probes. Calls are disjoint;
speaker/scenario overlap in this small roleplay corpus remains a limitation.
"""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path

from fetch_public_eval import BASE, fetch
from real_calls import normalized

HERE = Path(__file__).resolve().parent


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tree", type=Path, required=True)
    args = p.parse_args()
    directory = HERE / "data/real_calls/banking_training"
    directory.mkdir(parents=True, exist_ok=True)
    probes = [json.loads(s) for s in (HERE / "data/real_calls/hvb/probes.jsonl").read_text().splitlines()]
    excluded = {r["id"].split(":", 1)[1] for r in probes}
    seen = {normalized(r["text"]) for r in probes}
    paths = [x["path"] for x in json.loads(args.tree.read_text())["tree"]
             if x["path"].startswith("data/transcript/") and x["path"].endswith(".json") and Path(x["path"]).stem not in excluded]
    paths.sort(key=lambda x: hashlib.sha256(("bank-training-20261020:"+x).encode()).hexdigest())

    def one(path):
        data = fetch(BASE + path)
        turns = json.loads(data)
        text = "Caller: " + " ".join(t["human_transcript"] for t in turns if t["speaker_role"] == "agent")
        return {"id": "hvb:"+Path(path).stem, "label": 0, "text": text,
                "source": "hvb_recorded_roleplay_training", "url": BASE+path,
                "sha256": hashlib.sha256(data).hexdigest(), "label_quality": "benign_human_roleplay_not_organic_bank_traffic"}

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        fetched = list(pool.map(one, paths[:230]))
    rows = []
    for r in fetched:
        key = normalized(r["text"])
        if key in seen or len(key.split()) < 12:
            continue
        seen.add(key)
        rows.append(r)
    if len(rows) < 192:
        raise ValueError("Need 192 distinct new banking calls")
    for split, bank in (("train", rows[32:192]), ("validation", rows[:32])):
        authored = [json.loads(s) for s in (HERE/f"data/real_calls/hard_training/{split}.jsonl").read_text().splitlines()]
        combined = bank + authored
        (directory/f"{split}.jsonl").write_text("".join(json.dumps(r)+"\n" for r in combined))
    manifest = {"banking_train": 160, "banking_validation": 32, "authored_train": 104, "authored_validation": 24,
                "external_probe_id_overlap": 0, "normalized_exact_overlap": 0,
                "limits": "Call-disjoint and exact-text-disjoint, not speaker- or scenario-disjoint; development after inspected probes. Not a fresh blind test.",
                "source": "https://github.com/cricketclub/gridspace-stanford-harper-valley", "license": "CC BY 4.0",
                "rows": [{k:r[k] for k in ("id", "sha256", "url")} for r in rows[:192]]}
    (directory/"manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
    print(json.dumps({k:v for k,v in manifest.items() if k != "rows"}))


if __name__ == "__main__":
    main()
