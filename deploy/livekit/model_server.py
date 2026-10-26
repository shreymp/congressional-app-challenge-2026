"""One shared, loopback-only copy of both real models per cloud container."""
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[2]
LIVE = ROOT / "backend/AI Deepfake Pipeline/LiveKit Setup"
sys.path[:0] = [str(LIVE), str(LIVE.parent)]


def make_server(deepfake, jev, port=8000):
    voice_lock, text_lock = threading.Lock(), threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(30)

        def reply(self, status, data):
            body = json.dumps(data, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/health":
                return self.reply(200, {"ok": True, "modelLoaded": True, "deepfakeLoaded": True,
                                        "device": deepfake.device, "mode": "real", "meta": deepfake.meta,
                                        "jevVersion": getattr(jev, "version", None),
                                        "jevSha256": getattr(jev, "bundle_sha256", None),
                                        # Checkpoint hashes only; lets the agent bind calibration.json.
                                        "integrity": getattr(deepfake, "diagnostics", {}).get("integrity")})
            self.reply(404, {"error": "Not found"})

        def do_POST(self):
            if self.path not in ("/predict", "/deepfake"):
                return self.reply(404, {"error": "Not found"})
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 256000:
                    return self.reply(413, {"error": "Invalid body size"})
                body = self.rfile.read(size)
                if self.path == "/deepfake":
                    import numpy as np
                    if len(body) % 4 or len(body) > 16000 * 4 * 4:
                        raise ValueError("Invalid PCM window")
                    audio = np.frombuffer(body, dtype="<f4")
                    if not len(audio) or not np.isfinite(audio).all():
                        raise ValueError("Invalid PCM")
                    score = lambda: deepfake.score_window(audio)
                    lock = voice_lock
                else:
                    text = json.loads(body).get("transcript")
                    if not isinstance(text, str) or not text.strip() or len(text) > 20000:
                        raise ValueError("Invalid transcript")
                    score = lambda: {"probability": jev.score(text)}
                    lock = text_lock
            except (ValueError, TypeError, AttributeError, TimeoutError):
                return self.reply(400, {"error": "Invalid inference request"})
            if not lock.acquire(blocking=False):
                return self.reply(503, {"error": "Model busy"})
            try:
                result = score()
                if not all(type(v) in (int, float) and math.isfinite(v) for v in result.values()):
                    raise ValueError("Nonfinite inference result")
                self.reply(200, result)
            except Exception:
                self.reply(503, {"error": "Model inference failed"})
            finally:
                lock.release()

        def log_message(self, *_):
            pass  # Never print PCM, transcript bodies, or tokens.

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server


def main():
    import torch
    torch.set_num_threads(2)
    from detector_adapter import RealDetector
    deepfake = RealDetector()
    spec = importlib.util.spec_from_file_location("jev_model", ROOT / "backend/Transcript-Based Detector/model_service.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    jev = module.CallModel(Path(os.environ["JEV_MODEL_DIR"]), os.environ["JEV_MODEL_VERSION"])
    probability = jev.score("Caller: Read me the code your bank sent you.")
    if not math.isfinite(probability) or not 0 <= probability <= 1:
        raise RuntimeError("JEV startup inference failed")
    print(f"Real deepfake warm-up and JEV {jev.version} inference passed; sha256={jev.bundle_sha256}", flush=True)
    server = make_server(deepfake, jev)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
