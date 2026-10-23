"""Trace recorded Vosk prefixes without inventing prefix-level fraud labels.

Whole-call annotations cannot label every early greeting. Times below are ASR
checkpoints, not measured wall-clock warning latency or certified early recall.
"""
import argparse
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--checkpoint", type=Path, required=True)
    p.add_argument("--version", required=True)
    p.add_argument("--context-mode", choices=["tail", "windows"], default="tail")
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    spec = importlib.util.spec_from_file_location("service", HERE.parent/"Transcript-Based Detector/model_service.py")
    service = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(service)
    model = service.CallModel(args.checkpoint, args.version, bundle_manifest=args.checkpoint/"bundle.json", context_mode=args.context_mode)
    probes = [json.loads(s) for s in (HERE/"data/real_calls/audio_probes.jsonl").read_text().splitlines()]
    report = {"version": args.version, "modelSha256": model.bundle_sha256, "contextMode": args.context_mode, "warningThreshold": .75,
              "limits": "Development clips; FTC scripts may overlap training, banking is roleplay. Prefix labels not adjudicated. No early-recall or field-latency claim.", "clips": []}
    for row in probes:
        trace = []
        for prefix in row["prefixes"] + [{"seconds": row["duration_sec"], "text": row["text"]}]:
            try:
                score = model.score(prefix["text"])
                point = {"seconds": prefix["seconds"], "score": score, "guidance": score >= .75}
            except service.InsufficientEvidence:
                point = {"seconds": prefix["seconds"], "decision": "insufficient_evidence"}
            trace.append(point)
        report["clips"].append({"id": row["id"], "source": row["source"], "audio_sha256": row["audio_sha256"],
                                "duration_sec": row["duration_sec"], "whole_call_label": row["label"], "trace": trace})
    args.output.write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps({"clips": len(report["clips"]), "prefix_checkpoints": sum(len(r["trace"]) for r in report["clips"])}))


if __name__ == "__main__":
    main()
