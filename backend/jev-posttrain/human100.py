"""Freeze and score 50 YouTube human scambait excerpts + 50 natural calls.

Evaluation only: never fit weights/thresholds here. Public-source labels are
silver. YouTube excerpts are supplied by the corpus, not full-call transcripts.
"""
import argparse
import collections
import csv
import hashlib
import io
import json
import re
import urllib.parse
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data/real_calls/human100"
SEED = "human100-20261022:"
CHANNELS = {"JimBrowning", "ToniMosh", "scambaittv", "CJSCAMS", "ModderPaulScambaits",
            "ScammerAllergy", "FunGuyMediaScambaits", "DanGleeballsScambaiter"}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    return [json.loads(l) for l in path.read_text().splitlines() if l]


def build(scam_zip, swda_zip):
    from real_calls import normalized
    if DATA.exists():
        raise FileExistsError("Frozen evaluation already exists; use score")
    base = HERE / "data/real_calls"
    prior = [r for s in ("train", "validation", "test") for r in read(base / f"{s}.jsonl")]
    used_ids = {r["id"] for r in prior}
    used_speakers = {p for r in prior for p in r.get("speakers", [])}
    with zipfile.ZipFile(scam_zip) as z:
        candidates = list(csv.DictReader(io.StringIO(z.read("FullTranscriptData.csv").decode("utf-8-sig"))))
    candidates.sort(key=lambda r: sha((SEED + r["Source"]).encode()))
    scams, videos, channel_counts = [], set(), collections.Counter()
    for row in candidates:
        query = urllib.parse.parse_qs(urllib.parse.urlparse(row["Source"]).query)
        video = query.get("v", [""])[0]
        channel = query.get("ab_channel", [""])[0].strip()
        text = row["Content"].strip()
        if channel not in CHANNELS or not video or video in videos or channel_counts[channel] >= 12:
            continue
        if len(text.split()) < 45 or not any(w in text.lower() for w in ("how can i help", "how may i help", "yes", "yeah", "okay")):
            continue
        videos.add(video); channel_counts[channel] += 1
        scams.append({"id": "youtube:" + video, "label": 1, "text": "Conversation: " + text,
                      "source": "human_youtube_scambait_excerpt", "channel": channel,
                      "url": "https://www.youtube.com/watch?v=" + video,
                      "corpus_row": row["ID"], "label_quality": "source_attributed_scambait_not_independently_adjudicated",
                      "provenance": "recorded human scambait; source transcript excerpt, not full call; no speaker diarization"})
        if len(scams) == 50:
            break
    if len(scams) != 50:
        raise ValueError("Need 50 distinct human-channel videos")
    normals = []
    with zipfile.ZipFile(swda_zip) as outer:
        with zipfile.ZipFile(io.BytesIO(outer.read("swda-master/swda.zip"))) as archive:
            name = next(n for n in archive.namelist() if n.endswith("swda-metadata.csv"))
            meta = {r["conversation_no"]: r for r in csv.DictReader(io.StringIO(archive.read(name).decode()))}
            names = [n for n in archive.namelist() if n.startswith("swda/") and n.endswith(".utt.csv")]
            names.sort(key=lambda n: sha((SEED + n).encode()))
            for name in names:
                raw = archive.read(name)
                turns = list(csv.DictReader(io.StringIO(raw.decode())))
                m = meta[turns[0]["conversation_no"]]
                identity = "swda:" + m["conversation_no"]
                speakers = {m["from_caller"], m["to_caller"]}
                if identity in used_ids or speakers & used_speakers:
                    continue
                text = " ".join(t["text"] for t in turns)
                text = re.sub(r"\{[A-Z]+\s*|[{}\[\]+/#<>]", " ", text)
                words = text.split()
                length = len(scams[len(normals)]["text"].split()) - 1
                if len(words) < length:
                    continue
                normals.append({"id": identity, "label": 0, "text": "Conversation: " + " ".join(words[:length]),
                    "source": "natural_switchboard_excerpt", "speakers": sorted(speakers),
                    "url": "https://github.com/cgpotts/swda/blob/master/swda.zip", "archive_member": name,
                    "source_sha256": sha(raw), "category": m["topic_description"],
                    "label_quality": "natural_conversation_context_not_fraud_adjudicated",
                    "provenance": "recorded human dialogue; first words length matched to corresponding scam excerpt"})
                used_speakers.update(speakers)
                if len(normals) == 50:
                    break
    if len(normals) != 50:
        raise ValueError("Need 50 natural calls with previously unused and mutually disjoint speakers")
    rows = sorted(scams + normals, key=lambda r: sha((SEED + r["id"]).encode()))
    # Audit against raw real splits and all earlier gradient-training text.
    known = [r["text"] for r in prior]
    for path in (HERE / "data/prepared/train.jsonl", base / "banking_training/train.jsonl", base / "benign_prefix_training/train.jsonl"):
        known += [r["text"].split("Context:\n", 1)[-1].rsplit("\n\nEvaluate proposition:", 1)[0] for r in read(path)]
    def key(text):
        return normalized(re.sub(r"^(?:Conversation|Caller):\s*", "", text, flags=re.I))
    old = {key(t) for t in known}
    if any(key(r["text"]) in old for r in rows):
        raise ValueError("Evaluation text exactly overlaps known data")
    if len({key(r["text"]) for r in rows}) != 100:
        raise ValueError("Duplicate evaluation excerpt")
    from sklearn.feature_extraction.text import TfidfVectorizer
    x = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5)).fit_transform([key(t) for t in known] + [key(r["text"]) for r in rows])
    maxima = (x[len(known):] @ x[:len(known)].T).toarray().max(axis=1)
    for row, similarity in zip(rows, maxima):
        row["max_known_character_similarity"] = float(similarity)
    payload = "".join(json.dumps(r) + "\n" for r in rows)
    manifest = {"n": 100, "scam": 50, "normal": 50, "seed": SEED,
        "dataset_sha256": sha(payload.encode()), "inputs": {str(p): sha(p.read_bytes()) for p in (scam_zip, swda_zip)},
        "scam_channels": dict(channel_counts), "prior_normal_speaker_overlap": 0, "within_test_normal_speaker_overlap": 0,
        "exact_known_text_overlap": 0, "max_known_character_similarity": float(maxima.max()),
        "calls_with_similarity_at_least_0_8": int((maxima >= .8).sum()),
        "primary_threshold": .75, "secondary_threshold": .5, "context_mode": "windows",
        "scam_source": "https://www.kaggle.com/datasets/rivalcults/youtube-scam-phone-call-transcripts",
        "normal_source": "https://github.com/cgpotts/swda",
        "source_terms": "Kaggle metadata lists CC0; original videos retain creator rights. Switchboard corpus research terms apply. No raw data redistributed.",
        "limits": ["Source-attributed recorded human calls, not independently verified by listening to each video.",
                   "Scam-baiters are humans intentionally engaging scammers, not unsuspecting victims.",
                   "Source excerpts may precede decisive fraud evidence; labels describe source calls, not necessarily visible intent.",
                   "Scam and normal classes come from different sources. This is not field accuracy.",
                   "Mixed-speaker transcripts cannot establish live remote-speaker-only performance or ASR quality."]}
    DATA.mkdir(parents=True)
    (DATA / "test.jsonl").write_text(payload)
    (DATA / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def score(output):
    import torch
    from gliclass import GLiClassModel
    from transformers import AutoTokenizer
    from benchmark_real import infer, summarize
    manifest = json.loads((DATA / "manifest.json").read_text())
    if sha((DATA / "test.jsonl").read_bytes()) != manifest["dataset_sha256"]:
        raise ValueError("Frozen dataset was changed")
    rows = read(DATA / "test.jsonl")
    if len(rows) != 100 or collections.Counter(r["label"] for r in rows) != {0: 50, 1: 50}:
        raise ValueError("Exactly 50 scam and 50 normal required")
    if output.exists():
        raise FileExistsError(output)
    torch.set_num_threads(4)
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    report = {"manifest": manifest, "models": {}}
    results = []
    for name, checkpoint in (("v2", "call-v2-caller"), ("v5", "call-v5-balanced"), ("v6", "call-v6-prefix")):
        directory = HERE / "runs" / checkpoint
        tokenizer = AutoTokenizer.from_pretrained(directory, local_files_only=True)
        model = GLiClassModel.from_pretrained(directory, local_files_only=True).to(device)
        calibration = directory / "calibration.json"
        if name == "v2":
            calibration = HERE.parents[1] / "ios/ScamTranscript/Resources/JevCallV2/calibration.json"
        temperature = json.loads(calibration.read_text())["temperature"]
        ps = infer(model, tokenizer, rows, device, temperature, "windows")
        measured = summarize(rows, ps)
        a = measured["alert_at_0.75"]
        measured["accuracy_at_0.75"] = (100 - a["missed_scams"] - a["false_alerts"]) / 100
        report["models"][name] = {"checkpoint_sha256": sha((directory / "model.safetensors").read_bytes()),
            "temperature": temperature, "all": measured,
            "by_label": {str(y): summarize([r for r in rows if r["label"] == y], [p for r, p in zip(rows, ps) if r["label"] == y]) for y in (0, 1)}}
        for row, p in zip(rows, ps):
            results.append({"model": name, "id": row["id"], "source": row["source"], "url": row["url"],
                "label": row["label"], "score": p, "alert_at_0_75": p >= .75,
                "correct_at_0_75": (p >= .75) == bool(row["label"]), "text_sha256": sha(row["text"].encode())})
        print(json.dumps({"model": name, "accuracy_at_0.75": measured["accuracy_at_0.75"], **a}), flush=True)
        del model
        if device.type == "mps": torch.mps.empty_cache()
    output.mkdir(parents=True)
    (output / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    with (output / "model-evaluations.csv").open("w") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0]))
        writer.writeheader(); writer.writerows(results)
    index = {(r["model"], r["id"]): r for r in results}
    compact = []
    for row in rows:
        record = {k: row[k] for k in ("id", "source", "url", "label")}
        record["channel_or_topic"] = row.get("channel", row.get("category"))
        record["archive_member"] = row.get("archive_member", "")
        for name in ("v2", "v5", "v6"):
            r = index[name, row["id"]]
            record[name + "_score"] = r["score"]
            record[name + "_correct_at_0_75"] = r["correct_at_0_75"]
        compact.append(record)
    with (output / "100-tests.csv").open("w") as f:
        writer = csv.DictWriter(f, fieldnames=list(compact[0]))
        writer.writeheader(); writer.writerows(compact)
    (output / "source-manifest.json").write_text(json.dumps([{k: v for k, v in r.items() if k != "text"} for r in rows], indent=2) + "\n")
    return {name: r["all"]["accuracy_at_0.75"] for name, r in report["models"].items()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["build", "score"])
    parser.add_argument("--scam-zip", type=Path, default=Path("/tmp/jev-youtube-scam-transcripts.zip"))
    parser.add_argument("--swda-zip", type=Path, default=Path("/tmp/callshield-swda.zip"))
    parser.add_argument("--output", type=Path, default=HERE.parents[1] / "docs/testing/2026-10-22-human100")
    args = parser.parse_args()
    print(json.dumps(build(args.scam_zip, args.swda_zip) if args.action == "build" else score(args.output), indent=2))
