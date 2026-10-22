"""Export the experimental post-trained Jev call model and verify ONNX parity."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
import torch
from gliclass import GLiClassModel
from transformers import AutoTokenizer

from train import HERE, encode_rows, read_jsonl


class Wrapper(torch.nn.Module):
    def __init__(self, model):
        super().__init__()
        self.model = model

    def forward(self, input_ids, attention_mask):
        return self.model(input_ids=input_ids, attention_mask=attention_mask).logits


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for part in iter(lambda: f.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--checkpoint", type=Path, default=HERE / "runs" / "call-v1")
    args = p.parse_args()
    if not (args.checkpoint / "model.safetensors").is_file():
        raise FileNotFoundError("Post-trained checkpoint is missing")
    path = args.checkpoint / "model.onnx"
    tokenizer = AutoTokenizer.from_pretrained(args.checkpoint)
    model = GLiClassModel.from_pretrained(args.checkpoint).cpu().eval()
    examples = encode_rows(read_jsonl(HERE / "data" / "prepared" / "validation.jsonl")[:2], tokenizer, 300)
    inputs = tokenizer.pad({"input_ids": [r["ids"] for r in examples]}, padding=True, return_tensors="pt")
    wrapper = Wrapper(model).eval()
    with torch.no_grad():
        expected = wrapper(inputs["input_ids"], inputs["attention_mask"]).numpy()
    print(f"Exporting {path}", flush=True)
    torch.onnx.export(
        wrapper, (inputs["input_ids"], inputs["attention_mask"]), str(path),
        input_names=["input_ids", "attention_mask"], output_names=["logits"],
        dynamic_axes={"input_ids": {0: "batch", 1: "sequence"}, "attention_mask": {0: "batch", 1: "sequence"}, "logits": {0: "batch"}},
        opset_version=17, dynamo=False,
    )
    onnx.checker.check_model(str(path))
    session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    got = session.run(["logits"], {"input_ids": inputs["input_ids"].numpy().astype(np.int64), "attention_mask": inputs["attention_mask"].numpy().astype(np.int64)})[0]
    difference = float(np.max(np.abs(expected - got)))
    if difference > 1e-3:
        raise AssertionError(f"ONNX/PyTorch logits differ by {difference}")
    manifest = {"checkpoint": str(args.checkpoint), "checkpoint_sha256": sha256(args.checkpoint / "model.safetensors"), "onnx_sha256": sha256(path), "onnx_bytes": path.stat().st_size, "onnx_opset": 17, "max_logit_difference_on_two_validation_examples": difference, "deployment_status": "experimental; not copied into iOS"}
    (args.checkpoint / "export_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2), flush=True)


if __name__ == "__main__":
    main()
