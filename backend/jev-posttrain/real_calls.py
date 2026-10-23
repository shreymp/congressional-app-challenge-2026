"""Build an auditable research split; never infer fraud merely from 'robocall'.

Inputs are downloaded explicitly, never by the live service. FTC/NCSU labels are
silver: enforcement provenance plus a documented content filter, not human gold.
Switchboard negatives are natural recorded conversations, not business calls.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

HERE = Path(__file__).resolve().parent


def normalized(text):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z ]", " ", text.lower())).strip()


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def bucket(identity):
    value = int(digest(identity)[:8], 16) % 100
    return "train" if value < 70 else "validation" if value < 85 else "test"


def fraud_category(text):
    """Conservative selection in an enforcement corpus, NOT a deployed rule."""
    t = text.lower()
    if "social security" in t and re.search(r"suspend|suspension|block|enforcement|arrest|warrant", t):
        return "ssa_threat"
    if re.search(r"arrest warrant|federal custody|magistrate|grand jury|criminal offense", t):
        return "government_threat"
    if "amazon" in t and re.search(r"order|purchase|charge|transaction", t) and re.search(r"press|call us|call.*back", t):
        return "amazon_charge"
    return None


def build(ncsu: Path, swda: Path, output: Path):
    output.mkdir(parents=True, exist_ok=True)
    rows, skipped = [], 0
    seen = set()
    for r in csv.DictReader(ncsu.open()):
        category = fraud_category(r["transcript"])
        key = normalized(r["transcript"])
        if r["language"] != "en" or not category or len(key.split()) < 12 or key in seen:
            skipped += 1
            continue
        seen.add(key)
        rows.append({"id": r["file_name"], "text": "Caller: " + r["transcript"].strip(),
                     "label": 1, "source": "ncsu_ftc", "category": category,
                     "label_quality": "silver_enforcement_plus_content_filter",
                     "audio_url": "https://raw.githubusercontent.com/wspr-ncsu/robocall-audio-dataset/main/" + r["file_name"],
                     "case_pdf": r["case_pdf"]})
    # Connected components of similar scripts: duplicated recordings, numbers,
    # and ASR variants stay together. Category is not used as a model feature.
    matrix = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5)).fit_transform([normalized(r["text"]) for r in rows])
    similarity = (matrix @ matrix.T).toarray()
    parent = list(range(len(rows)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, j in zip(*np.where(np.triu(similarity >= .65, 1))):
        parent[root(j)] = root(i)
    groups = {}
    for i in range(len(rows)):
        groups.setdefault(root(i), []).append(i)
    for members in groups.values():
        identity = min(digest(normalized(rows[i]["text"])) for i in members)
        for i in members:
            rows[i].update(group=identity, split=bucket(identity))

    with zipfile.ZipFile(swda) as outer:
        with zipfile.ZipFile(io.BytesIO(outer.read("swda-master/swda.zip"))) as archive:
            metadata_name = next(n for n in archive.namelist() if n.endswith("swda-metadata.csv"))
            meta = {r["conversation_no"]: r for r in csv.DictReader(io.StringIO(archive.read(metadata_name).decode()))}
            counts = {s: 0 for s in ("train", "validation", "test")}
            for name in sorted(n for n in archive.namelist() if n.startswith("swda/") and n.endswith(".utt.csv")):
                turns = list(csv.DictReader(io.StringIO(archive.read(name).decode())))
                m = meta[turns[0]["conversation_no"]]
                # A speaker is assigned globally, including across conversations.
                a, b = bucket("speaker:" + m["from_caller"]), bucket("speaker:" + m["to_caller"])
                if a != b or counts[a] >= {"train": 260, "validation": 65, "test": 80}[a]:
                    continue
                text = " ".join(t["text"] for t in turns if t["caller"] == "A")
                text = re.sub(r"\{[A-Z]+\s*|[{}\[\]+/#<>]", " ", text)
                text = re.sub(r"\s+", " ", text).strip()
                if len(text.split()) < 35:
                    continue
                # Match live bounded caller-only text. No topic metadata in input.
                text = text[-5500:]
                rows.append({"id": "swda:" + m["conversation_no"], "text": "Caller: " + text,
                             "label": 0, "source": "switchboard", "category": m["topic_description"],
                             "label_quality": "natural_conversation_context_not_fraud_annotation",
                             "group": m["conversation_no"], "speakers": [m["from_caller"], m["to_caller"]], "split": a})
                counts[a] += 1
    for split in ("train", "validation", "test"):
        selected = [r for r in rows if r["split"] == split]
        (output / f"{split}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in selected))
    sources = {"ncsu": "https://github.com/wspr-ncsu/robocall-audio-dataset",
               "switchboard": "https://github.com/cgpotts/swda",
               "switchboard_citation": "Jurafsky, Shriberg, and Biasca (1997), Switchboard SWBD-DAMSL; Stolcke et al. (2000)",
               "licensing": "NCSU data public domain; Switchboard corpus CC BY-NC-SA 3.0 per upstream corpus, code GPL2. Local research only; do not redistribute raw corpus in app."}
    report = {"sources": sources, "input_sha256": {str(p.name): hashlib.sha256(p.read_bytes()).hexdigest() for p in (ncsu, swda)},
              "selection": "English, >=12 words; three explicit impersonation/threat categories only; excluded marketing and ambiguous recordings",
              "ncsu_excluded": skipped, "scam_script_groups": len(groups), "similarity_group_threshold": .65,
              "counts": {s: {str(y): sum(r["split"] == s and r["label"] == y for r in rows) for y in (0, 1)} for s in ("train", "validation", "test")},
              "limitations": ["Silver scam annotations and context-derived normal labels are not a human-reviewed gold benchmark.",
                              "Scam and normal classes come from different sources: source/style confounding remains.",
                              "Only three fraud families and casual English conversations; no claim for all calls.",
                              "FTC videos may overlap training scripts; keep these audio probes and authored contrasts separate from independent evaluation."]}
    (output / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--ncsu", type=Path, required=True)
    p.add_argument("--swda", type=Path, required=True)
    p.add_argument("--output", type=Path, default=HERE / "data/real_calls")
    args = p.parse_args()
    build(args.ncsu, args.swda, args.output)
