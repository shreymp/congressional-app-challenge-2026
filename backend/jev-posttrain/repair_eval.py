"""Freeze validation/test sets, fit validation-only policies, then evaluate once.

Research transcripts only. Source-attributed YouTube excerpts are silver labels;
this cannot establish live/audio or field accuracy. No raw text is published.
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
DATA = HERE / "data/real_calls"
SEED = "jev-repair-v7-20261022:"
OUT = HERE.parents[1] / "docs/testing/2026-10-22-jev-v7"
FROZEN = DATA / "repair_v7"
TEST_CHANNELS = {"scambaittv", "CJSCAMS", "ToniMosh", "JimBrowning", "ScammerAllergy", "DanGleeballsScambaiter"}


def sha(value):
    return hashlib.sha256(value).hexdigest()


def read(path):
    return [json.loads(s) for s in path.read_text().splitlines() if s]


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def build(scam_zip, swda_zip, sbc_zip):
    from real_calls import normalized
    from sklearn.feature_extraction.text import TfidfVectorizer
    if FROZEN.exists() or OUT.exists():
        raise FileExistsError("Frozen V7 protocol/data already exists")
    paths = [DATA / f"{s}.jsonl" for s in ("train", "validation", "test")]
    paths += [DATA / "banking_training" / f"{s}.jsonl" for s in ("train", "validation")]
    paths += [DATA / "human100/test.jsonl", DATA / "hvb/probes.jsonl", DATA / "fresh_banking/probes.jsonl"]
    paths = [p for p in paths if p.exists()]
    prior = [r for p in paths for r in read(p)]
    used_ids = {r["id"] for r in prior}
    used_speakers = {s for r in prior for s in r.get("speakers", [])}
    with zipfile.ZipFile(scam_zip) as archive:
        raw = list(csv.DictReader(io.StringIO(archive.read("FullTranscriptData.csv").decode("utf-8-sig"))))
    raw.sort(key=lambda r: sha((SEED + r["Source"]).encode()))
    seen, candidates = set(), []
    for row in raw:
        q = urllib.parse.parse_qs(urllib.parse.urlparse(row["Source"]).query)
        video, channel = q.get("v", [""])[0], q.get("ab_channel", [""])[0].strip()
        identity = "youtube:" + video
        if not video or identity in used_ids or identity in seen or len(row["Content"].split()) < 45:
            continue
        if channel not in TEST_CHANNELS | {"ModderPaulScambaits"}:
            continue
        seen.add(identity)
        candidates.append({"id": identity, "source": "human_youtube_scambait_excerpt", "channel": channel,
                           "label": 1, "text": "Conversation: " + row["Content"].strip(),
                           "url": "https://www.youtube.com/watch?v=" + video,
                           "label_quality": "source_call_silver_not_excerpt_adjudicated"})
    texts = [normalized(r["text"]) for r in prior + candidates]
    matrix = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5)).fit_transform(texts)
    chosen, positive = [], {"calibration": [], "test": []}
    max_similarity = {"calibration": 0.0, "test": 0.0}
    for i, row in enumerate(candidates, len(prior)):
        split = "calibration" if row["channel"] == "ModderPaulScambaits" else "test"
        if len(positive[split]) >= {"calibration": 20, "test": 30}[split]:
            continue
        comparison = list(range(len(prior))) + chosen
        similarity = float((matrix[i] @ matrix[comparison].T).max())
        if similarity >= .8:
            continue
        positive[split].append(row)
        chosen.append(i)
        max_similarity[split] = max(max_similarity[split], similarity)
    if [len(positive[s]) for s in ("calibration", "test")] != [20, 30]:
        raise ValueError("Not enough disjoint eligible human-source excerpts; do not weaken the audit")
    negative = {"calibration": [], "test": []}
    with zipfile.ZipFile(swda_zip) as outer:
        with zipfile.ZipFile(io.BytesIO(outer.read("swda-master/swda.zip"))) as archive:
            metadata = next(n for n in archive.namelist() if n.endswith("swda-metadata.csv"))
            meta = {r["conversation_no"]: r for r in csv.DictReader(io.StringIO(archive.read(metadata).decode()))}
            names = sorted((n for n in archive.namelist() if n.startswith("swda/") and n.endswith(".utt.csv")),
                           key=lambda n: sha((SEED + n).encode()))
            for name in names:
                turns = list(csv.DictReader(io.StringIO(archive.read(name).decode())))
                info = meta[turns[0]["conversation_no"]]
                split = "calibration" if len(negative["calibration"]) < 2 else "test"
                identity = "swda:" + info["conversation_no"]
                speakers = {info["from_caller"], info["to_caller"]}
                if identity in used_ids or used_speakers & speakers:
                    continue
                text = re.sub(r"\{[A-Z]+\s*|[{}\[\]+/#<>]", " ", " ".join(t["text"] for t in turns))
                words = text.split()
                count = len(positive[split][len(negative[split])]["text"].split()) - 1
                if len(words) < count:
                    continue
                negative[split].append({"id": identity, "source": "natural_switchboard_excerpt", "label": 0,
                    "text": "Conversation: " + " ".join(words[:count]), "speakers": sorted(speakers),
                    "url": "https://github.com/cgpotts/swda/blob/master/swda.zip", "archive_member": name,
                    "label_quality": "natural_conversation_context_not_fraud_adjudicated"})
                used_speakers.update(speakers)
                if len(negative["test"]) == 2:
                    break
    if [len(negative[s]) for s in ("calibration", "test")] != [2, 2]:
        raise ValueError("Need four remaining speaker-disjoint Switchboard pairs")
    # New normal source is held entirely out of training and calibration.
    # Exclude public lectures, sermons and scripted/public storytelling segments
    # from the source descriptions, before scoring any model.
    exclude = {12, 20, 21, 25, 27, 30, 38, 40, 54, 55, 60}
    with zipfile.ZipFile(sbc_zip) as archive:
        names = sorted((n for n in archive.namelist() if re.fullmatch(r"TRN/SBC\d{3}\.trn", n)),
                       key=lambda n: sha((SEED + n).encode()))
        for name in names:
            number = int(Path(name).stem[3:])
            if number in exclude:
                continue
            raw = archive.read(name)
            spoken, speakers = [], set()
            for line in raw.decode("utf-8-sig", errors="replace").splitlines():
                match = re.match(r"^\s*[\d.]+\s+[\d.]+\s+(.*)", line)
                if not match:
                    continue
                part = match[1]
                tag = re.match(r"([A-Z][A-Z_0-9 ]*):\s*(.*)", part)
                if tag:
                    speakers.add(tag[1].strip())
                    part = tag[2]
                part = re.sub(r"\([^)]*\)|<[^>]*>|\b(?:X+|Hx?|TSK)\b", " ", part)
                part = re.sub(r"[\[\]@=%~<>_]|\d", "", part)
                spoken.extend(part.split())
            if len(speakers) < 2:
                continue
            count = len(positive["test"][len(negative["test"])]["text"].split()) - 1
            if len(spoken) < count:
                continue
            negative["test"].append({"id": "sbc:" + Path(name).stem, "source": "natural_santa_barbara_excerpt",
                "label": 0, "text": "Conversation: " + " ".join(spoken[:count]),
                "url": "https://www.linguistics.ucsb.edu/sites/default/files/sitefiles/research/SBC/" + Path(name).name,
                "archive_member": name, "source_sha256": sha(raw), "speaker_pseudonyms": sorted(speakers),
                "label_quality": "natural_interaction_context_not_fraud_adjudicated"})
            if len(negative["test"]) == 30:
                break
    if len(negative["test"]) != 30:
        raise ValueError("Need 28 new multi-person Santa Barbara conversations")
    # Exact-text audit includes both classes and all known prior call sources.
    used_text = {normalized(r["text"]) for r in prior}
    for split in ("calibration", "test"):
        for row in positive[split] + negative[split]:
            key = normalized(row["text"])
            if key in used_text:
                raise ValueError("Repeated transcript text")
            used_text.add(key)
    # Reuse explicitly identified validation-only normals; never borrow test
    # examples to fill calibration. These 18 are NOT counted as new examples.
    legacy_normals = [r for r in read(DATA / "validation.jsonl") if r["label"] == 0]
    legacy_normals.sort(key=lambda r: sha((SEED + r["id"]).encode()))
    negative["calibration"] += [{**r, "previously_seen_validation": True} for r in legacy_normals[:18]]
    FROZEN.mkdir(parents=True)
    OUT.mkdir(parents=True)
    hashes, source_rows = {}, []
    for split in ("calibration", "test"):
        rows = sorted(positive[split] + negative[split], key=lambda r: sha((SEED + r["id"]).encode()))
        payload = "".join(json.dumps(r) + "\n" for r in rows).encode()
        (FROZEN / f"{split}.jsonl").write_bytes(payload)
        hashes[split] = sha(payload)
        source_rows += [{"split": split, **{k: v for k, v in r.items() if k != "text"},
                         "text_sha256": sha(r["text"].encode())} for r in rows]
    # Existing roleplay validation adds legitimate banking contexts to threshold
    # constraints. It never supplies the natural-call primary test result.
    bank_path = DATA / "banking_training/validation.jsonl"
    protocol = {"seed": SEED, "dataset_sha256": hashes,
        "input_sha256": {str(p): sha(p.read_bytes()) for p in paths + [scam_zip, swda_zip, sbc_zip]},
        "calibration": {"human_excerpts": 40, "new_human_excerpts": 22, "previously_seen_validation_normals": 18, "scams": 20, "normal": 20,
                        "banking_roleplay_validation": str(bank_path), "banking_sha256": sha(bank_path.read_bytes())},
        "fresh_test": {"n": 60, "scams": 30, "normal": 30},
        "source_split": "New calibration scams: ModderPaulScambaits. New test scams: other named creators. Creators overlap the previously inspected human100 development sample.",
        "operating_requirements": {"min_recall": .9, "max_fpr_each_benign_domain": .05},
        "fresh_acceptance": {"min_accuracy": .9, "min_recall": .9, "max_fpr": .05,
                             "no_additional_fn_or_fp_vs_baseline_fixed_0_75": True},
        "context_mode": "windows", "maximum_scam_similarity_to_prior_or_other_selected": max_similarity,
        "forbidden": "Never fit weights, cutoff, temperature or select epochs with test labels. Failed policy fits remain failed. No retry on these test answers.",
        "limits": ["Transcript excerpts, not full audio calls; no ASR or audio performance measured.",
                   "Silver source-call labels can overstate visible excerpt evidence; each video was not independently listened to.",
                   "Scam and normal source confounding remains. No field accuracy guarantee or deployment approval.",
                   "28/30 test normals are new-source Santa Barbara conversations, mostly face-to-face. Some within-corpus speakers can recur; no independent-call confidence claim.",
                   "Santa Barbara corpus: Du Bois et al. 2000-2005, UCSB; CC BY-ND 3.0 US. Local evaluation only; raw/processed text is not redistributed or trained on.",
                   "Banking threshold constraints use previously seen human roleplay validation, not organic banking calls."]}
    save(OUT / "protocol.json", protocol)
    save(OUT / "source-manifest.json", source_rows)
    return protocol


def evaluate():
    import torch
    from gliclass import GLiClassModel
    from transformers import AutoTokenizer
    from benchmark_real import infer
    from training_safety import confusion, fit_operating_point
    protocol = json.loads((OUT / "protocol.json").read_text())
    result_dir = OUT / "evaluation"
    if result_dir.exists():
        raise FileExistsError("Evaluation already exists; do not retune/retry on these answers")
    for split, expected in protocol["dataset_sha256"].items():
        if sha((FROZEN / f"{split}.jsonl").read_bytes()) != expected:
            raise ValueError("Frozen input changed")
    bank_path = Path(protocol["calibration"]["banking_roleplay_validation"])
    if sha(bank_path.read_bytes()) != protocol["calibration"]["banking_sha256"]:
        raise ValueError("Banking validation changed")
    calibration = read(FROZEN / "calibration.jsonl")
    calibration += [r for r in read(bank_path) if r["source"] == "hvb_recorded_roleplay_training"]
    result_dir.mkdir()
    torch.set_num_threads(4)
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    fitted = {}
    fit_records = []
    candidate_manifest = json.loads((HERE / "runs/call-v7-guarded/train_manifest.json").read_text())
    chosen = next(r for r in candidate_manifest["history"] if r["epoch"] == candidate_manifest["selected_epoch"])
    if not chosen["eligible"] or not all(g["passed"] for g in chosen["regression_gates"].values()):
        raise ValueError("Selected checkpoint lacks passing training regression gates")
    # Finish fitting BOTH policies before any fresh-test inference/metrics.
    for name, directory in (("v5", HERE / "runs/call-v5-balanced"), ("v7", HERE / "runs/call-v7-guarded")):
        tokenizer = AutoTokenizer.from_pretrained(directory, local_files_only=True)
        model = GLiClassModel.from_pretrained(directory, local_files_only=True).to(device)
        temperature = json.loads((directory / "calibration.json").read_text())["temperature"]
        scores = infer(model, tokenizer, calibration, device, temperature, "windows")
        policy = fit_operating_point(calibration, scores, min_recall=.9, max_fpr=.05)
        policy |= {"checkpoint_sha256": sha((directory / "model.safetensors").read_bytes()),
                   "tokenizer_sha256": sha((directory / "tokenizer.json").read_bytes()),
                   "temperature": temperature, "context_mode": "windows", "checkpoint": str(directory),
                   "protocol_sha256": sha((OUT / "protocol.json").read_bytes()), "research_only": True}
        save(result_dir / f"{name}-decision-policy.json", policy)
        fitted[name] = policy
        fit_records += [{"model": name, "id": r["id"], "source": r["source"], "label": r["label"],
                         "score": score, "url": r.get("url", "")} for r, score in zip(calibration, scores)]
        del model
        if device.type == "mps": torch.mps.empty_cache()
    # Persisting this record before test access establishes the frozen choices.
    save(result_dir / "policies-frozen-before-test.json", fitted)
    with (result_dir / "validation-scores.csv").open("w") as output:
        writer = csv.DictWriter(output, fieldnames=list(fit_records[0]))
        writer.writeheader()
        writer.writerows(fit_records)
    report, records = {"protocol": protocol, "models": {}}, []
    sets = {"fresh_human60": read(FROZEN / "test.jsonl"), "inspected_human100_development": read(DATA / "human100/test.jsonl")}
    for name, policy in fitted.items():
        directory = Path(policy["checkpoint"])
        tokenizer = AutoTokenizer.from_pretrained(directory, local_files_only=True)
        model = GLiClassModel.from_pretrained(directory, local_files_only=True).to(device)
        metrics = {}
        for split, rows in sets.items():
            scores = infer(model, tokenizer, rows, device, policy["temperature"], "windows")
            metrics[split] = {"original_0_75": confusion(rows, scores, .75),
                             "validation_selected_policy": confusion(rows, scores, policy["threshold"]) if policy["passed"] else None}
            metrics[split]["by_source"] = {}
            for source in sorted({r["source"] for r in rows}):
                selected = [(r, score) for r, score in zip(rows, scores) if r["source"] == source]
                sr, sp = map(list, zip(*selected))
                metrics[split]["by_source"][source] = {"original_0_75": confusion(sr, sp, .75),
                    "validation_selected_policy": confusion(sr, sp, policy["threshold"]) if policy["passed"] else None}
            for row, score in zip(rows, scores):
                records.append({"model": name, "set": split, "id": row["id"], "label": row["label"],
                                "source": row["source"], "url": row.get("url", ""), "score": score,
                                "policy_threshold": policy["threshold"],
                                "policy_alert": score >= policy["threshold"] if policy["passed"] else None})
        report["models"][name] = {"policy": policy, "sets": metrics}
        del model
        if device.type == "mps": torch.mps.empty_cache()
    baseline = report["models"]["v5"]["sets"]["fresh_human60"]["original_0_75"]
    candidate = report["models"]["v7"]["sets"]["fresh_human60"]["validation_selected_policy"]
    failures = []
    if candidate is None:
        failures.append("No validation operating point met the frozen recall/false-alert requirements")
    else:
        for key, target in (("accuracy", .9), ("recall", .9)):
            if candidate[key] < target: failures.append(f"Fresh {key} below {target}")
        if candidate["false_positive_rate"] > .05: failures.append("Fresh false-alert rate exceeds .05")
        for key in ("fn", "fp"):
            if candidate[key] > baseline[key]: failures.append(f"Fresh {key} worse than V5 fixed-cutoff baseline")
    report["decision"] = {"passed_this_research_gate": not failures, "failures": failures,
                          "deployment_approved": False,
                          "remaining_requirements": "Independent excerpt adjudication, legitimate business diversity, full-call ASR/caller-only evaluation and ONNX/native parity before deployment"}
    report["training_selection"] = {"selected_epoch": candidate_manifest["selected_epoch"],
                                     "improved_checkpoint": candidate_manifest["improved_checkpoint"]}
    save(result_dir / "results.json", report)
    with (result_dir / "predictions.csv").open("w") as output:
        writer = csv.DictWriter(output, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["build", "evaluate"])
    parser.add_argument("--scam-zip", type=Path, default=Path("/tmp/jev-youtube-scam-transcripts.zip"))
    parser.add_argument("--swda-zip", type=Path, default=Path("/tmp/callshield-swda.zip"))
    parser.add_argument("--sbc-zip", type=Path, default=Path("/tmp/jev-sbcorpus.zip"))
    args = parser.parse_args()
    print(json.dumps(build(args.scam_zip, args.swda_zip, args.sbc_zip), indent=2)) if args.action == "build" else evaluate()
