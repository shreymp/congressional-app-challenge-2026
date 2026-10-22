#!/usr/bin/env python3
"""Download the exact upstream ONNX model used by this repository."""
import argparse
import hashlib
import os
from pathlib import Path
import tempfile
import urllib.request

REVISION = "8af2496eb63c7fa66d7d234e1f62629380030eb4"
URL = f"https://huggingface.co/heman10x/rlcd-modernbert-151m/resolve/{REVISION}/model.onnx"
SHA256 = "4ae01f822538b000fa0e55859d4b3e6b40871d860149397e8784428b2a42ee5e"
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "verdict-151m/model.onnx"


def digest(path):
    checksum = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            checksum.update(chunk)
    return checksum.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    target = args.output.resolve()
    if target.is_file() and digest(target) == SHA256:
        print(f"Already verified: {target}")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        print("Downloading ONNX model (606 MB)...", flush=True)
        checksum = hashlib.sha256()
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".jev-", delete=False) as output:
            temporary = Path(output.name)
            with urllib.request.urlopen(URL, timeout=120) as response:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
                    checksum.update(chunk)
        if checksum.hexdigest() != SHA256:
            raise RuntimeError("Model checksum mismatch; download rejected")
        os.replace(temporary, target)
        print(f"Downloaded and verified: {target}")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
