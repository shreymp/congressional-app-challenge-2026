"""Verify that source snapshots match the pinned Git blob IDs (no network required)."""
from pathlib import Path
import hashlib
import json

root = Path(__file__).resolve().parent
manifest = json.loads((root / "source_manifest.json").read_text())
for item in manifest:
    data = (root / item["snapshot_path"]).read_bytes()
    actual = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    if actual != item["sha"]:
        raise SystemExit(f"SHA mismatch: {item['snapshot_path']}: {actual} != {item['sha']}")
print(f"PASS: {len(manifest)} snapshot files match pinned repository blob IDs")
