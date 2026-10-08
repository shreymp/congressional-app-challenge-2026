"""Small qualitative guardrail for the app's existing ten Jev propositions.

This does not measure signal accuracy; it reveals whether the whole-call
fine-tuned checkpoints can be safely reused as the ten-signal iOS model.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import torch
from gliclass import GLiClassModel
from transformers import AutoTokenizer

from train import HERE, ROOT

sys.path.insert(0, str(ROOT / "backend" / "jev-prototype"))
from jev_scam_signals import CONTRAST_CASES, SIGNALS, KevScamSignalModel  # noqa: E402


def main() -> None:
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    report = {}
    for name, path in (("call-v1", HERE / "runs" / "call-v1"), ("call-v2-caller", HERE / "runs" / "call-v2-caller")):
        tok = AutoTokenizer.from_pretrained(path)
        model = GLiClassModel.from_pretrained(path).to(device).eval()
        report[name] = {}
        for case, transcript in CONTRAST_CASES.items():
            prompts = [KevScamSignalModel._render(s.proposition, transcript) for s in SIGNALS]
            inputs = tok(prompts, padding=True, return_tensors="pt").to(device)
            with torch.no_grad():
                logits = model(**inputs).logits[:, :3].float()
                p = torch.softmax(logits, dim=-1)
                conditional_yes = (p[:, 0] / (p[:, 0] + p[:, 1])).cpu().tolist()
            report[name][case] = {s.id: round(float(prob), 6) for s, prob in zip(SIGNALS, conditional_yes, strict=True)}
        del model
        if device.type == "mps": torch.mps.empty_cache()
    target = HERE / "runs" / "signal-probe.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
