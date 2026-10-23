"""Create a checksummed local bundle and verify real ONNX service parity.

Does not copy weights into the app, change a running service, or publish models.
"""
import argparse
import hashlib
import importlib.util
import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--checkpoint", type=Path, required=True)
    p.add_argument("--version", choices=["V3", "V4", "V5"], required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    directory = args.checkpoint.resolve()
    manifest = [{"version": args.version, "files": {name: {"sha256": hashlib.sha256((directory/name).read_bytes()).hexdigest(),
        "bytes": (directory/name).stat().st_size} for name in ("model.onnx", "tokenizer.json", "calibration.json")}}]
    bundle = directory / "bundle.json"
    bundle.write_text(json.dumps(manifest, indent=2)+"\n")
    spec = importlib.util.spec_from_file_location("service", HERE.parent / "Transcript-Based Detector/model_service.py")
    service = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(service)
    model = service.CallModel(directory, args.version, bundle_manifest=bundle)
    from transformers import AutoTokenizer
    import torch
    from gliclass import GLiClassModel
    from benchmark_real import infer
    torch.set_num_threads(4)
    tokenizer = AutoTokenizer.from_pretrained(directory, local_files_only=True)
    reference = GLiClassModel.from_pretrained(directory, local_files_only=True).cpu()
    rows = [json.loads(line) for line in (HERE / "data/real_calls/test.jsonl").read_text().splitlines()][:8]
    rows += [{**r, "source": "authored_contrast"} for r in json.loads((HERE/"contrast_probes.json").read_text())[:8]]
    rows += [{"id": "long", "label": 1, "text": rows[-1]["text"] + " Please wait for the next screen to load. "*70}]
    rows += [json.loads(line) for line in (HERE / "data/real_calls/audio_probes.jsonl").read_text().splitlines()]
    result = {"version": args.version, "bundle": manifest, "modes": {}}
    for mode in ("tail", "windows"):
        model.context_mode = mode
        expected = infer(reference, tokenizer, rows, torch.device("cpu"), model.temperature, mode)
        started = time.monotonic()
        got = [model.assess(r["text"]) for r in rows]
        elapsed = time.monotonic()-started
        diff = max(abs(a-b["probability"]) for a,b in zip(expected, got))
        if diff > 1e-4:
            raise AssertionError(f"Service parity failure: {diff}")
        result["modes"][mode] = {"n": len(rows), "max_probability_difference": diff, "mean_cpu_service_ms": elapsed/len(rows)*1000,
                                 "max_windows": max(r["windows"] for r in got), "parity_passed": True}
    try:
        model.assess("Caller: hello")
        raise AssertionError("Greeting must abstain")
    except service.InsufficientEvidence:
        result["short_greeting_abstains"] = True
    model.context_mode = "tail"
    server = service.make_server(model, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    try:
        for endpoint in ("/predict", "/assess"):
            request = urllib.request.Request(url+endpoint, data=json.dumps({"transcript": rows[-1]["text"]}).encode(), headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=5) as response:
                got = json.load(response)
            expected = model.score(rows[-1]["text"])
            assert abs(expected-got["probability"]) < 1e-6
            if endpoint == "/assess":
                assert got["modelVersion"] == args.version
                assert got["calibratedOnRealCalls"] is False
        request = urllib.request.Request(url+"/predict", data=json.dumps({"transcript": "Caller: hello"}).encode(), headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(request, timeout=5)
            raise AssertionError("Greeting HTTP must abstain")
        except urllib.error.HTTPError as error:
            assert error.code == 422
            with error:
                assert json.load(error)["decision"] == "insufficient_evidence"
        result["real_onnx_http_predict_assess_and_abstention"] = True
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
