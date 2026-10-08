"""Kev transcript-signal extraction with the OpenJev/Verdict 151M ONNX model.

This module intentionally has no audio/deepfake processing and no final scam
classifier. Its only output is independent evidence for ten caller behaviors.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

MODEL_REPOSITORY = "heman10x/rlcd-modernbert-151m"
DEFAULT_MODEL_DIR = Path(__file__).resolve().parents[2] / "verdict-151m"
ARTIFACTS = [
    "model.onnx",
    "tokenizer.json",
    "tokenizer_config.json",
    "config.json",
    "calibrator.json",
    "bundle_manifest.json",
]


@dataclass(frozen=True)
class Signal:
    id: str
    label: str
    proposition: str


SIGNALS: tuple[Signal, ...] = (
    Signal("money_request", "Money request", "The caller is asking the other person to pay, send, transfer, withdraw, or provide money or something of monetary value."),
    Signal("credentials_request", "Credentials request", "The caller is asking the other person for a password, PIN, login credential, account password, or security answer."),
    Signal("verification_code_request", "Verification-code request", "The caller is asking the other person to share a one-time passcode, verification code, authentication code, or code sent by text or email."),
    Signal("personal_info_request", "Personal-information request", "The caller is asking the other person for sensitive personal information such as a Social Security number, date of birth, address, bank account number, or card number."),
    Signal("urgency", "Urgency", "The caller says that the other person must act immediately, today, right now, or before an urgent deadline."),
    Signal("pressure", "Pressure to decide", "The caller is pressuring the other person to make a quick decision or complete an action without time to think or verify."),
    Signal("fear_or_threat", "Fear or threat", "The caller is using a threat, frightening consequence, punishment, account loss, arrest, or other fear to influence the other person."),
    Signal("secrecy_request", "Secrecy request", "The caller is telling the other person to keep the situation secret or not contact family, a bank, police, or another trusted person."),
    Signal("unusual_payment_method", "Unusual payment method", "The caller is requesting payment by gift card, cryptocurrency, wire transfer, cash deposit, payment app, or another unusual hard-to-reverse method."),
    Signal("impersonation_claim", "Impersonation claim", "The caller claims to be a bank, government agency, police officer, company, technical support provider, relative, or other authority or known person."),
)


@dataclass(frozen=True)
class SignalResult:
    id: str
    label: str
    probability: float
    insufficient_evidence_probability: float
    raw_yes_probability: float
    raw_no_probability: float


class KevScamSignalModel:
    """A one-call, batched adapter for Kev-style transcript questions."""

    def __init__(self, model_dir: str | Path = DEFAULT_MODEL_DIR, max_transcript_tokens: int = 350) -> None:
        self.model_dir = Path(model_dir)
        missing = [name for name in ARTIFACTS if not (self.model_dir / name).is_file()]
        if missing:
            raise FileNotFoundError(
                f"Missing Verdict artifacts: {', '.join(missing)}. "
                "Run `python jev_scam_signals.py --download-model`."
            )
        if not 16 <= max_transcript_tokens < 512:
            raise ValueError("max_transcript_tokens must be between 16 and 511")

        import onnxruntime as ort
        from transformers import AutoTokenizer

        self.max_transcript_tokens = max_transcript_tokens
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_dir)
        options = ort.SessionOptions()
        options.intra_op_num_threads = 4
        options.inter_op_num_threads = 1
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(self.model_dir / "model.onnx", options, providers=["CPUExecutionProvider"])
        calibration = json.loads((self.model_dir / "calibrator.json").read_text())
        self.temperature = float(calibration.get("per_k", {}).get("3", calibration["temperature"]))

    @staticmethod
    def _render(proposition: str, transcript: str) -> str:
        labels = (
            f"<<LABEL>>true: {proposition}"
            f"<<LABEL>>false: not {proposition}"
            "<<LABEL>>insufficient evidence"
        )
        return f"{labels}<<SEP>>Context:\n{transcript}\n\nEvaluate proposition: {proposition}"

    def _trim(self, transcript: str) -> tuple[str, bool, int]:
        text = " ".join(transcript.split())
        if not text:
            raise ValueError("transcript must not be empty")
        ids = self.tokenizer(text, add_special_tokens=False)["input_ids"]
        trimmed = len(ids) > self.max_transcript_tokens
        if trimmed:
            text = self.tokenizer.decode(ids[-self.max_transcript_tokens :], skip_special_tokens=True)

        # Reserve room for the longest label/question shell in the exported
        # 512-token model; retain the newest transcript words if necessary.
        while max(len(self.tokenizer(self._render(signal.proposition, text))["input_ids"]) for signal in SIGNALS) > 512:
            ids = self.tokenizer(text, add_special_tokens=False)["input_ids"]
            if len(ids) <= 16:
                raise ValueError("signal prompt cannot fit Verdict's 512-token limit")
            text = self.tokenizer.decode(ids[-(len(ids) - 16) :], skip_special_tokens=True)
            trimmed = True
        return text, trimmed, len(self.tokenizer(text, add_special_tokens=False)["input_ids"])

    @staticmethod
    def _softmax(logits: np.ndarray, temperature: float) -> np.ndarray:
        scaled = logits.astype(np.float64) / temperature
        exp = np.exp(scaled - scaled.max(axis=-1, keepdims=True))
        return exp / exp.sum(axis=-1, keepdims=True)

    def score(self, transcript: str) -> dict[str, Any]:
        text, trimmed, token_count = self._trim(transcript)
        prompts = [self._render(signal.proposition, text) for signal in SIGNALS]
        encoded = self.tokenizer(prompts, padding=True, truncation=False, return_tensors="np")
        start = time.perf_counter()
        logits = self.session.run(
            ["logits"],
            {"input_ids": encoded["input_ids"].astype(np.int64), "attention_mask": encoded["attention_mask"].astype(np.int64)},
        )[0]
        scores = self._softmax(logits[:, :3], self.temperature)
        results = []
        for signal, (yes, no, abstain) in zip(SIGNALS, scores, strict=True):
            yes, no, abstain = float(yes), float(no), float(abstain)
            results.append(asdict(SignalResult(
                id=signal.id,
                label=signal.label,
                probability=yes / (yes + no) if yes + no else 0.5,
                insufficient_evidence_probability=abstain,
                raw_yes_probability=yes,
                raw_no_probability=no,
            )))
        return {
            "signals": {item["id"]: item for item in results},
            "telemetry": {
                "forward_call_count": 1,
                "latency_ms": round((time.perf_counter() - start) * 1000, 2),
                "transcript_was_trimmed": trimmed,
                "transcript_tokens": token_count,
            },
        }


def download_model(destination: Path) -> None:
    from huggingface_hub import snapshot_download

    snapshot_download(repo_id=MODEL_REPOSITORY, local_dir=str(destination), allow_patterns=ARTIFACTS)


DEMO = "Caller: This is Officer Davis with the police department. You need to act right now. Buy $500 in gift cards and read the numbers to me. Do not tell your family or bank."

CONTRAST_CASES = {
    "obvious_code_scam": "Caller: I am from your bank fraud department. Read me the six-digit code we just texted you, and do not tell your bank branch or anyone in your family.",
    "dentist_reschedule": "Caller: Hi, this is Maple Dental. We need to reschedule your cleaning from Tuesday to Thursday. Does 3 p.m. work for you?",
}


VerdictScamSignalModel = KevScamSignalModel


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Kev transcript-signal prototype using Verdict 151M ONNX")
    parser.add_argument("transcript", nargs="?", help="Rolling call transcript")
    parser.add_argument("--demo", action="store_true", help="Run the included sample transcript")
    parser.add_argument("--contrast-check", action="store_true", help="Compare an obvious scam transcript against a benign transcript")
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--download-model", action="store_true", help="Download the public Verdict ONNX artifact")
    args = parser.parse_args(argv)
    if args.download_model:
        download_model(args.model_dir)
        print(f"Downloaded Verdict artifacts to {args.model_dir}")
        return 0
    if args.contrast_check:
        model = KevScamSignalModel(args.model_dir)
        print(json.dumps({name: model.score(text) for name, text in CONTRAST_CASES.items()}, indent=2))
        return 0
    transcript = DEMO if args.demo else args.transcript
    if not transcript:
        parser.error("provide a transcript or use --demo")
    print(json.dumps(KevScamSignalModel(args.model_dir).score(transcript), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
