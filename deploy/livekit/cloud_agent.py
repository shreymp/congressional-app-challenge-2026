"""Direct LiveKit agent entrypoint with supervised, private model services."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
LIVE = ROOT / "backend/AI Deepfake Pipeline/LiveKit Setup"


def health(url, data=None):
    body = None if data is None else json.dumps(data).encode()
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


class Services:
    def __init__(self):
        self.children = []
        self.stopping = threading.Event()

    def start(self):
        sys.path.insert(0, str(LIVE))
        from recording_notice import read_notice
        read_notice()  # Missing/invalid disclosure must fail image checks and startup.
        print("Recording notice asset validated", flush=True)
        self.children.append(subprocess.Popen([sys.executable, str(Path(__file__).with_name("model_server.py"))]))
        self.children.append(subprocess.Popen(["node", str(ROOT / "backend/Transcript-Based Detector/server.js")]))
        deadline = time.monotonic() + 210
        while time.monotonic() < deadline:
            if any(child.poll() is not None for child in self.children):
                raise RuntimeError("Cloud inference service exited before readiness")
            try:
                ready = health("http://127.0.0.1:8000/health")
                connector = health("http://127.0.0.1:3000/health")
                if ready.get("deepfakeLoaded") and ready.get("modelLoaded") and connector.get("modelConfigured"):
                    result = health("http://127.0.0.1:3000/v1/jev/probability", {"transcript": "Caller: Read me the bank security code."})
                    if type(result.get("probability")) in (int, float) and 0 <= result["probability"] <= 1:
                        print("Cloud backend ready: real deepfake + JEV + connector", flush=True)
                        sys.path.insert(0, str(LIVE))
                        import transcript_pipeline
                        if transcript_pipeline.load_model() is None:
                            raise RuntimeError("Cloud transcription must be enabled")
                        print("Cloud Vosk model load passed", flush=True)
                        threading.Thread(target=self.monitor, daemon=True).start()
                        return
            except (OSError, ValueError):
                pass
            time.sleep(1)
        raise RuntimeError("Cloud models did not become ready within 210 seconds")

    def monitor(self):
        while not self.stopping.wait(2):
            if any(child.poll() is not None for child in self.children):
                print("Cloud inference service stopped; stopping worker for restart", flush=True)
                os.kill(os.getpid(), signal.SIGTERM)
                return

    def close(self):
        self.stopping.set()
        for child in self.children:
            if child.poll() is None:
                child.terminate()
        for child in self.children:
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


if __name__ == "__main__":
    # This image always serves the deepfake model from model_server.py. Pin it here so a
    # mistyped deployment secret can never send job processes looking for local weights.
    os.environ["DETECTOR"] = "remote"
    os.environ["DETECTOR_SERVICE_URL"] = "http://127.0.0.1:8000"
    services = Services()
    try:
        services.start()
        sys.path.insert(0, str(LIVE))
        import agent
        agent.cli.run_app(agent.server)
    finally:
        services.close()
