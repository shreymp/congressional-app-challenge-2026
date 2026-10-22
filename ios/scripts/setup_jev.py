#!/usr/bin/env python3
"""Prepare pinned on-device Jev assets, reusing the repository's local model."""
import hashlib
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT.parent
MODEL_FILES = {
    "model.onnx": "4ae01f822538b000fa0e55859d4b3e6b40871d860149397e8784428b2a42ee5e",
    "tokenizer.json": "8bb449eb0c037aae44115b65905bb339b8f3f74eb37067c19127feb3c0755723",
    "calibrator.json": "af2a876993148efa0726b6ccf710fe2303897d20c0ce8c7c9036eb50f64d23de",
}

def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            value.update(chunk)
    return value.hexdigest()

def fetch(url, path, expected):
    print(f"Downloading {url}", flush=True)
    with urllib.request.urlopen(url, timeout=120) as response, path.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)
    if digest(path) != expected:
        raise RuntimeError(f"Checksum mismatch for {url}; refusing changed assets")

destination = ROOT / "ScamTranscript/Resources/Jev"
destination.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix="scam-jev-") as temporary:
    temporary = Path(temporary)
    for name, expected in MODEL_FILES.items():
        target = destination / name
        if target.is_file() and digest(target) == expected:
            print(f"Already verified: {name}")
            continue
        local = REPOSITORY / "verdict-151m" / name
        if local.is_file():
            if digest(local) != expected:
                raise RuntimeError(f"Local {name} differs from the tested bundle")
            shutil.copy2(local, target)
        else:
            download = temporary / name
            fetch(f"https://huggingface.co/heman10x/rlcd-modernbert-151m/resolve/8af2496eb63c7fa66d7d234e1f62629380030eb4/{name}", download, expected)
            shutil.copy2(download, target)
        print(f"Verified: {name}", flush=True)
    runtime = ROOT / "Vendor/ONNXRuntime"
    if not (runtime / "onnxruntime.xcframework/Info.plist").is_file():
        archive = temporary / "onnxruntime.zip"
        fetch("https://download.onnxruntime.ai/pod-archive-onnxruntime-c-1.24.3.zip", archive,
              "b7eedc45932bac758ffd057cac0feb3f682269e47750b159e4c865145cbf0a8e")
        runtime.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive) as zipped:
            for member in zipped.infolist():
                if not (runtime / member.filename).resolve().is_relative_to(runtime.resolve()):
                    raise RuntimeError("Unsafe archive member")
            zipped.extractall(runtime)
print("Jev is ready. Rebuild ScamTranscript in Xcode.")
