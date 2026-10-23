"""Loopback-only HTTP adapter for the existing post-trained Jev call ONNX bundle.

Run after `python ios/scripts/setup_posttrained_jev.py` from the repository root.
Uses the same prompt, last 300 context tokens and binary calibration as iOS's
JevCallDecisionMaker. This experimental score is not calibrated on real calls.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROPOSITION = "The caller is attempting to scam or defraud the other person."


def render_prompt(text: str) -> str:
    return (f"<<LABEL>>true: {PROPOSITION}<<LABEL>>false: not {PROPOSITION}"
            f"<<LABEL>>insufficient evidence<<SEP>>Context:\n{text}"
            f"\n\nEvaluate proposition: {PROPOSITION}")


def clean_context(text: str) -> str:
    # These are classifier control tokens, never caller-authored labels.
    return re.sub(r"<<(?:LABEL|SEP)>>", " ", text, flags=re.I).strip()


def context_windows(tokenizer, transcript: str, mode: str = "tail") -> tuple[list[str], bool]:
    """Bound inference while retaining early evidence in optional window mode.

    Max pooling is an experimental risk score, not a calibrated probability.
    Coverage is reported when the request exceeds the six-window budget.
    """
    text = clean_context(transcript)
    ids = tokenizer.encode(text, add_special_tokens=False).ids
    if mode not in ("tail", "windows"):
        raise ValueError("invalid context mode")
    if len(ids) <= 300:
        return [text], True
    if mode == "tail":
        return [tokenizer.decode(ids[-300:], skip_special_tokens=True)], False
    starts = list(range(0, len(ids) - 300, 225)) + [len(ids) - 300]
    if len(starts) > 6:
        starts = [starts[round(i * (len(starts) - 1) / 5)] for i in range(6)]
    covered = all(b <= a + 300 for a, b in zip(starts, starts[1:]))
    return [tokenizer.decode(ids[start:start+300], skip_special_tokens=True) for start in starts], covered


class InsufficientEvidence(ValueError):
    pass


def calibrated_probability(yes: float, no: float, temperature: float) -> float:
    if not all(math.isfinite(x) for x in (yes, no, temperature)) or temperature <= 0:
        raise ValueError("invalid model logits or calibration")
    margin = (yes - no) / temperature
    return 1 / (1 + math.exp(-margin)) if margin >= 0 else math.exp(margin) / (1 + math.exp(margin))


class CallModel:
    def __init__(self, directory: Path, version: str = "V2", *, bundle_manifest: Path | None = None,
                 context_mode: str = "tail"):
        # Check that ONNX, tokenizer and calibration are the SAME published bundle.
        manifest = json.loads((bundle_manifest or ROOT / "backend/jev-posttrain/model_downloads.json").read_text())
        bundle = next(x for x in manifest if x["version"] == version)
        for name, asset in bundle["files"].items():
            with (directory / name).open("rb") as source:
                actual = hashlib.file_digest(source, "sha256").hexdigest()
            if actual != asset["sha256"]:
                raise ValueError(f"bundle checksum mismatch: {name}")
        from tokenizers import Tokenizer
        import onnxruntime as ort

        self.tokenizer = Tokenizer.from_file(str(directory / "tokenizer.json"))
        self.tokenizer.no_truncation()
        self.tokenizer.no_padding()
        self.temperature = float(json.loads((directory / "calibration.json").read_text())["temperature"])
        self.version, self.context_mode = version, context_mode
        self.bundle_sha256 = bundle["files"]["model.onnx"]["sha256"]
        calibrated_probability(0, 0, self.temperature)
        options = ort.SessionOptions()
        options.intra_op_num_threads = 4
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(directory / "model.onnx"), options,
                                            providers=["CPUExecutionProvider"])

    def score(self, transcript: str) -> float:
        return self.assess(transcript)["probability"]

    def assess(self, transcript: str) -> dict:
        import numpy as np
        text = clean_context(transcript)
        # Greetings/silence are not negative evidence of fraud. Never return 0.
        meaningful = re.sub(r"^(?:caller|receiver):\s*", "", text, flags=re.I)
        if len(re.findall(r"\w+", meaningful)) < 4:
            raise InsufficientEvidence("Need more caller speech")
        windows, covered = context_windows(self.tokenizer, text, self.context_mode)
        encoded = [self.tokenizer.encode(render_prompt(window)).ids for window in windows]
        length = max(map(len, encoded))
        if length > 512:
            raise ValueError("Jev prompt exceeds 512 tokens")
        pad = self.tokenizer.token_to_id("[PAD]")
        if pad is None:
            raise ValueError("Tokenizer is missing padding token")
        ids = np.array([row + [pad] * (length-len(row)) for row in encoded], dtype=np.int64)
        mask = np.array([[1]*len(row) + [0]*(length-len(row)) for row in encoded], dtype=np.int64)
        logits = self.session.run(["logits"], {
            "input_ids": ids, "attention_mask": mask,
        })[0]
        probabilities = [calibrated_probability(float(row[0]), float(row[1]), self.temperature) for row in logits]
        return {"probability": max(probabilities), "scoreType": "experimental_transcript_risk",
                "calibratedOnRealCalls": False, "modelVersion": self.version,
                "contextMode": self.context_mode, "windows": len(windows), "contextCovered": covered,
                "modelSha256": self.bundle_sha256}


def make_server(model, port: int = 8000) -> ThreadingHTTPServer:
    inference_lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def reply(self, status, body):
            payload = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            if self.path == "/health":
                return self.reply(200, {"ok": True, "modelLoaded": True})
            self.reply(404, {"error": "Not found"})

        def do_POST(self):
            if self.path not in ("/predict", "/assess"):
                return self.reply(404, {"error": "Not found"})
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 32768:
                    return self.reply(413, {"error": "Invalid body size"})
                body = json.loads(self.rfile.read(size))
                text = body.get("transcript") if isinstance(body, dict) else None
                if not isinstance(text, str) or not text.strip() or len(text) > 20000:
                    return self.reply(400, {"error": "Expected a nonempty transcript"})
            except (ValueError, TimeoutError):
                return self.reply(400, {"error": "Invalid request"})
            # Do not accumulate inference behind another call beyond the connector deadline.
            if not inference_lock.acquire(blocking=False):
                return self.reply(503, {"error": "Model busy; retry latest context"})
            try:
                assessment = model.assess(text) if hasattr(model, "assess") else {"probability": model.score(text)}
                probability = assessment["probability"]
                if type(probability) not in (int, float) or not math.isfinite(probability) or not 0 <= probability <= 1:
                    raise ValueError("invalid probability")
                result = assessment if self.path == "/assess" else {"probability": probability}
            except InsufficientEvidence:
                return self.reply(422, {"error": "Insufficient transcript evidence", "decision": "insufficient_evidence"})
            except Exception:
                return self.reply(503, {"error": "Model inference unavailable"})
            finally:
                inference_lock.release()
            self.reply(200, result)

        def log_message(self, *_):
            pass  # no request bodies or transcripts in logs

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", choices=["V1", "V2", "V3", "V4", "V5"], default="V2")
    parser.add_argument("--bundle-manifest", type=Path, help="Explicit checksummed local research bundle manifest")
    parser.add_argument("--context-mode", choices=["tail", "windows"], default="tail")
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    directory = args.model_dir or Path(os.environ.get("JEV_MODEL_DIR") or
                                      ROOT / f"ios/ScamTranscript/Resources/JevCall{args.version}")
    if args.version in ("V3", "V4", "V5") and not args.bundle_manifest:
        parser.error("Research models require an explicit local --bundle-manifest")
    model = CallModel(directory, args.version, bundle_manifest=args.bundle_manifest, context_mode=args.context_mode)
    server = make_server(model, args.port)
    print(f"Jev {args.version} loaded; http://127.0.0.1:{args.port}/predict", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
