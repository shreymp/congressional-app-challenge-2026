"""Fetch fixed public banking-roleplay probes, kept outside training.

HVB contains recorded HUMAN roleplay, not organic customer-support traffic.
"""
import argparse
import concurrent.futures
import hashlib
import json
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = "https://raw.githubusercontent.com/cricketclub/gridspace-stanford-harper-valley/master/"


def fetch(url):
    with urllib.request.urlopen(url, timeout=30) as response:
        return response.read()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tree", type=Path, required=True)
    p.add_argument("--output", type=Path, default=HERE / "data/real_calls/hvb")
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    paths = sorted(x["path"] for x in json.loads(args.tree.read_text())["tree"] if x["path"].startswith("data/transcript/"))
    paths.sort(key=lambda x: hashlib.sha256(("20261020:" + x).encode()).hexdigest())
    selected = paths[:40]

    def one(path):
        sid = Path(path).stem
        data = fetch(BASE + path)
        (args.output / f"{sid}.json").write_bytes(data)
        turns = json.loads(data)
        # Agent is the bank employee, who is the remote speaker when the user
        # calls their bank. This is a deliberately difficult benign contrast.
        text = "Caller: " + " ".join(t["human_transcript"] for t in turns if t["speaker_role"] == "agent")
        return {"id": "hvb:" + sid, "text": text, "label": 0, "source": "hvb_recorded_roleplay", "split": "external_probe",
                "label_quality": "recorded_human_roleplay_benign_scenario", "url": BASE + path,
                "sha256": hashlib.sha256(data).hexdigest(), "audio_url": BASE + f"data/audio/agent/{sid}.wav"}

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(one, selected))
    for row in rows[:3]:
        data = fetch(row["audio_url"])
        sid = row["id"].split(":")[1]
        (args.output / f"{sid}.wav").write_bytes(data)
        row["audio_sha256"] = hashlib.sha256(data).hexdigest()
    (args.output / "probes.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    print(f"Fetched {len(rows)} recorded banking roleplays and 3 agent audio tracks; never used for training.")


if __name__ == "__main__":
    main()
