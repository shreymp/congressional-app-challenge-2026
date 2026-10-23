"""Score one call transcript with the experimental post-trained Jev checkpoint."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import torch
from gliclass import GLiClassModel
from transformers import AutoTokenizer

from train import HERE, PROPOSITION, encode_rows


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("text", nargs="?", help="Call transcript; reads stdin when omitted")
    p.add_argument("--checkpoint", type=Path, default=HERE / "runs" / "call-v1")
    p.add_argument("--policy", type=Path, help="Explicit validation-fitted research decision policy; rejects failed/mismatched policies")
    args = p.parse_args()
    text = args.text if args.text is not None else sys.stdin.read()
    if not text.strip():
        p.error("Provide a call transcript as an argument or on stdin")
    if args.policy:
        policy = json.loads(args.policy.read_text())
        from training_safety import validate_decision_policy
        try:
            validate_decision_policy(policy, args.checkpoint)
        except (ValueError, KeyError, OSError) as error:
            p.error(str(error))
        from benchmark_real import infer
        tokenizer = AutoTokenizer.from_pretrained(args.checkpoint, local_files_only=True)
        device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
        model = GLiClassModel.from_pretrained(args.checkpoint, local_files_only=True).to(device).eval()
        value = infer(model, tokenizer, [{"id": "manual", "text": text, "label": 0}], device,
                      policy["temperature"], "windows")[0]
        print(json.dumps({"scam_score": value, "warning_threshold": policy["threshold"],
                          "decision": "alert" if value >= policy["threshold"] else "no_alert",
                          "score_type": "experimental_transcript_risk", "research_only": True}, indent=2))
        return
    tokenizer = AutoTokenizer.from_pretrained(args.checkpoint)
    row = {"text": f"Context:\n{text.strip()}\n\nEvaluate proposition: {PROPOSITION}", "target_id": "false", "source": "manual", "text_sha256": "manual"}
    encoded = encode_rows([row], tokenizer, 300)[0]
    inputs = tokenizer.pad({"input_ids": [encoded["ids"]]}, padding=True, return_tensors="pt")
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    model = GLiClassModel.from_pretrained(args.checkpoint).to(device).eval()
    with torch.no_grad():
        logits = model(**{k: v.to(device) for k, v in inputs.items() if k in ("input_ids", "attention_mask")}).logits[0, :3].float()
        raw = torch.softmax(logits, dim=-1).cpu().tolist()
    evaluation = args.checkpoint / "evaluation.json"
    calibration = args.checkpoint / "calibration.json"
    temperature = 1.0
    if calibration.exists():
        temperature = float(json.loads(calibration.read_text())["temperature"])
    elif evaluation.exists():
        temperature = float(json.loads(evaluation.read_text())["models"]["candidate"]["validation_temperature"])
    calibrated = torch.sigmoid((logits[0] - logits[1]) / temperature).item()
    print(json.dumps({
        "proposition": PROPOSITION,
        "scam_score": round(calibrated, 6),
        "decision_at_0_5": "scam" if calibrated >= .5 else "not_scam",
        "raw_yes_no_insufficient": [round(x, 6) for x in raw],
        "temperature": temperature,
        "calibration_scope": json.loads(calibration.read_text()).get("scope", "historical experimental calibration") if calibration.exists() else "synthetic phone-call validation only",
        "deployment_status": "experimental transcript scorer; field accuracy not established",
    }, indent=2))


if __name__ == "__main__":
    main()
