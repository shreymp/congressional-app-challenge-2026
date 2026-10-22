"""Exploratory research comparison: real/silver, roleplay, authored probes separate.

No fitting on test data. Thresholds are declared before scoring. Per-record output
is local and ignored; the aggregate result can be committed without source text.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import re
import time
from pathlib import Path

import numpy as np
import torch
from gliclass import GLiClassModel
from transformers import AutoTokenizer

from train import HERE, DATA, caller_only, encode_rows, predict, read_jsonl
from evaluate import binary_metrics, sigmoid
from finetune_real import as_training

spec = importlib.util.spec_from_file_location("service", HERE.parent / "Transcript-Based Detector/model_service.py")
service = importlib.util.module_from_spec(spec)
spec.loader.exec_module(service)


def wilson(success, n):
    if not n:
        return None
    z = 1.959963984540054
    p = success/n
    center = (p+z*z/(2*n))/(1+z*z/n)
    half = z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/(1+z*z/n)
    return [center-half, center+half]


def summarize(rows, probabilities):
    labels = np.array([0 if r["label"] else 1 for r in rows])
    p = np.array(probabilities)
    result = binary_metrics(labels, p)
    correct = int(((p >= .5) == (labels == 0)).sum())
    result["accuracy_wilson_95"] = wilson(correct, len(rows))
    result["accuracy_wilson_assumption"] = "Descriptive iid approximation only. Related scripts/speakers and adaptive benchmark reuse invalidate independent-sample generalization claims."
    chosen = (p <= .2) | (p >= .8)
    result["selective_0.2_0.8"] = {"coverage": float(chosen.mean()), "abstentions": int((~chosen).sum()),
        "accuracy_on_answered": float(((p[chosen] >= .5) == (labels[chosen] == 0)).mean()) if chosen.any() else None,
        "warning": "Threshold-only coverage on these non-short samples. Accuracy excludes abstentions; not overall accuracy or full service coverage."}
    result["alert_at_0.75"] = {"missed_scams": int(((p < .75) & (labels == 0)).sum()),
                              "false_alerts": int(((p >= .75) & (labels == 1)).sum())}
    return result


def infer(model, tokenizer, rows, device, temperature, mode="tail"):
    from tokenizers import Tokenizer
    raw_tokenizer = Tokenizer.from_str(tokenizer.backend_tokenizer.to_str())
    raw_tokenizer.no_padding(); raw_tokenizer.no_truncation()
    encoded, owner = [], []
    for i,r in enumerate(rows):
        meaningful = re.sub(r"^(?:caller|receiver):\s*", "", service.clean_context(r["text"]), flags=re.I)
        if len(re.findall(r"\w+", meaningful)) < 4:
            raise ValueError("Short speech must be evaluated as abstention with streaming_probe.py, not forced into binary accuracy")
        windows, _ = service.context_windows(raw_tokenizer, r["text"], mode)
        for text in windows:
            ids = tokenizer(service.render_prompt(text), truncation=False)["input_ids"]
            if len(ids) > 512:
                raise ValueError("oversize prompt")
            encoded.append({"ids": ids, "target": 0 if r["label"] else 1})
            owner.append(i)
    logits, _ = predict(model, encoded, tokenizer, device, 8)
    probabilities = sigmoid((logits[:,0]-logits[:,1])/temperature)
    result = [0.0]*len(rows)
    for i,p in zip(owner, probabilities):
        result[i] = max(result[i], float(p))
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", type=Path, default=HERE / "data/real_calls")
    p.add_argument("--candidate", type=Path, default=HERE / "runs/call-v3-real")
    p.add_argument("--candidate-name", default="v3")
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    torch.set_num_threads(4)
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    test = read_jsonl(args.data / "test.jsonl")
    contrasts = [{**r, "source": "authored_contrast", "text": r["text"]} for r in json.loads((HERE / "contrast_probes.json").read_text())]
    early = next(r["text"] for r in contrasts if r["id"] == "bank_otp_theft")
    contrasts.append({"id": "early_scam_then_long_neutral_tail", "label": 1, "source": "authored_contrast",
                      "text": early + " Please wait while the system loads the next screen. We are still connected. "*50})
    hvb = read_jsonl(args.data / "hvb/probes.jsonl")
    audio = read_jsonl(args.data / "audio_probes.jsonl")
    prior_test = read_jsonl(DATA / "test.jsonl")
    prior_rows = []
    for i, r in enumerate(prior_test):
        try:
            raw = caller_only(r)
        except ValueError:
            continue
        text = raw["text"].split("Context:\n", 1)[1].rsplit("\n\nEvaluate proposition:", 1)[0]
        prior_rows.append({"id": f"prior:{i}", "label": int(r["target_id"] == "true"), "source": r["source"], "text": text})
    sets = {"recorded_group_heldout": test, "banking_recorded_roleplay_external": hvb,
            "authored_development_probes": contrasts, "public_audio_vosk_probes": audio,
            "prior_synthetic_caller_test_exploratory": prior_rows}
    report = {"thresholds": {"binary": .5, "in_call_warning": .75, "selective_low": .2, "selective_high": .8},
              "data_manifest": json.loads((args.data / "manifest.json").read_text()), "models": {},
              "limits": ["Not a 99% claim. Only a small, selected English benchmark.", "FTC YouTube scripts can overlap NCSU training; audio probes are exploratory, not independent calls.",
                         "Banking audio is human roleplay; Switchboard is natural conversation.", "No real-world probability calibration, blinded human adjudication, or field deployment established.",
                         "These probes were repeatedly inspected and informed V4/V5 development. Held out from gradient training does not mean a fresh blind test.",
                         "Per-call Wilson intervals assume iid samples; positive recorded tests cover only four script groups and negative conversations share speakers. Intervals are descriptive, not confidence in field accuracy."]}
    per_item = []
    for name, directory in (("v2", HERE / "runs/call-v2-caller"), (args.candidate_name, args.candidate)):
        print(f"Loading {name}", flush=True)
        tokenizer = AutoTokenizer.from_pretrained(directory, local_files_only=True)
        model = GLiClassModel.from_pretrained(directory, local_files_only=True).to(device)
        calibration = directory / "calibration.json"
        if name == "v2":
            calibration = HERE.parents[1] / "ios/ScamTranscript/Resources/JevCallV2/calibration.json"
        temperature = json.loads(calibration.read_text())["temperature"]
        scores = {"temperature": temperature, "checkpoint": str(directory),
                  "checkpoint_sha256": hashlib.sha256((directory / "model.safetensors").read_bytes()).hexdigest(), "sets": {}}
        for set_name, rows in sets.items():
            started = time.monotonic()
            modes = ("tail", "windows") if set_name != "prior_synthetic_caller_test_exploratory" else ("tail",)
            scores["sets"][set_name] = {}
            for mode in modes:
                ps = infer(model, tokenizer, rows, device, temperature, mode)
                measured = summarize(rows, ps)
                measured["elapsed_sec"] = time.monotonic()-started
                scores["sets"][set_name][mode] = measured
                for r, probability in zip(rows, ps):
                    per_item.append({"model": name, "set": set_name, "mode": mode, "id": r["id"], "label": r["label"], "score": probability,
                                     "text_sha256": hashlib.sha256(r["text"].encode()).hexdigest()})
                print(json.dumps({"model": name, "set": set_name, "mode": mode, **measured}), flush=True)
        report["models"][name] = scores
        del model
        if device.type == "mps":
            torch.mps.empty_cache()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+"\n")
    (args.data / f"{args.candidate_name}_benchmark_predictions.jsonl").write_text("".join(json.dumps(r)+"\n" for r in per_item))


if __name__ == "__main__":
    main()
