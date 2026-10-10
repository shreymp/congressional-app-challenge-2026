#!/usr/bin/env python3
"""Fetch pinned Vosk assets. No network access is needed by the built app."""
import hashlib
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = [
    ("https://github.com/santalex/libvosk/releases/download/v0.3.50/libvosk-v0.3.50-ios-xcframework.zip",
     "13348851e77887fec83631e1651655057801677472dfd0a53f1670cbe06eb735", ROOT / "Vendor"),
    ("https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip",
     "30f26242c4eb449f948e42cb302dd7a686cb29a3423a8367f99ff41780942498", ROOT / "ScamTranscript/Resources"),
]
with tempfile.TemporaryDirectory(prefix="scam-vosk-") as temporary:
    for index, (url, expected, destination) in enumerate(ASSETS):
        archive = Path(temporary) / f"asset-{index}.zip"
        print(f"Downloading {url}", flush=True)
        with urllib.request.urlopen(url, timeout=120) as response, archive.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        actual = hashlib.sha256(archive.read_bytes()).hexdigest()
        if actual != expected:
            raise RuntimeError(f"Checksum mismatch: {url}; expected {expected}, got {actual}")
        destination.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive) as zipped:
            for member in zipped.infolist():
                resolved = (destination / member.filename).resolve()
                if not resolved.is_relative_to(destination.resolve()):
                    raise RuntimeError("Unsafe archive member")
            zipped.extractall(destination)
        print(f"Verified and extracted to {destination}", flush=True)
print("Open ios/ScamTranscript.xcodeproj and run ScamTranscript.")
