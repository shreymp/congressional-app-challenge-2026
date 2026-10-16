"""Exercise actual container model services, independent of LiveKit credentials."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request


def main():
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("cloud_entry", Path(__file__).with_name("cloud_agent.py"))
    entry = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(entry)
    services = entry.Services()
    try:
        services.start()
        import numpy as np
        import soundfile as sf
        from scipy.signal import resample_poly
        wav = Path(sys.argv[1])
        audio, rate = sf.read(wav, dtype="float32", always_2d=True)
        from math import gcd
        audio = resample_poly(audio.mean(axis=1), 16000 // gcd(rate, 16000), rate // gcd(rate, 16000))
        request = urllib.request.Request("http://127.0.0.1:8000/deepfake",
            data=np.asarray(audio[:64000], dtype="<f4").tobytes(), headers={"Content-Type": "application/octet-stream"})
        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.load(response)
        assert 0 <= result["p_fake"] <= 1 and result["infer_ms"] >= 0
        sys.path.insert(0, str(root / "backend/AI Deepfake Pipeline/LiveKit Setup"))
        import transcript_pipeline
        # Exercise the exact STT -> connector -> calibrated model path through its async pipeline.
        import asyncio
        async def text_test():
            pipeline = transcript_pipeline.for_call(transcript_pipeline.load_model())
            pipeline.start()
            try:
                samples = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
                for offset in range(0, len(samples), 320):
                    pipeline.push(samples[offset:offset + 320].tobytes())
                    await asyncio.sleep(.02)
                deadline = time.monotonic() + 40
                while time.monotonic() < deadline:
                    status = pipeline.snapshot()
                    if status["state"] == "monitoring" and status["probability"] is not None:
                        print("REAL MODELS PASSED", json.dumps({"deepfake_infer_ms": result["infer_ms"],
                              "transcript_state": status["state"], "scored_revision": status.get("scored_revision")}))
                        return
                    await asyncio.sleep(.5)
                raise RuntimeError("Fixture did not produce a transcript probability")
            finally:
                await pipeline.aclose()
        asyncio.run(text_test())
    finally:
        services.close()


if __name__ == "__main__":
    main()
