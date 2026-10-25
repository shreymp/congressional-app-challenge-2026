"""Local, offline model bundle verification before deserializing any checkpoint."""
from pathlib import Path
import hashlib
import json

HERE = Path(__file__).resolve().parent
PIN_FILE = HERE / "model_integrity.json"


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_bundle(folder, *, manifest_path=PIN_FILE):
    folder = Path(folder)
    manifest = json.loads(Path(manifest_path).read_text())
    paths = {"architecture": HERE / "architecture/config.json",
             "detector_config": folder / "detector_config.json"}
    paths["checkpoint"] = next((folder / name for name in ("detector_state.pt", "best.pt")
                                 if (folder / name).is_file()), folder / "best.pt")
    hashes = {}
    for key, path in paths.items():
        actual = sha256(path)
        if actual != manifest["sha256"][key]:
            raise ValueError(f"Model integrity check failed for {key}")
        hashes[key] = actual
    return {"sha256": hashes, "architecture_revision": manifest["architecture_revision"],
            "architecture_path": str(paths["architecture"]), "checkpoint_path": str(paths["checkpoint"])}


def pin_bundle(folder, *, manifest_path=PIN_FILE):
    """Rewrite the pin file for a new, reviewed bundle (e.g. after post-training).

    Keeps the architecture source/revision. Run it once, review the diff, and update the
    checkpoint hash in deploy/livekit/prepare.py and the benchmark config to match.
    """
    folder = Path(folder)
    manifest = json.loads(Path(manifest_path).read_text())
    checkpoint = next((folder / name for name in ("detector_state.pt", "best.pt") if (folder / name).is_file()), None)
    if checkpoint is None:
        raise FileNotFoundError("No detector_state.pt or best.pt in the bundle")
    manifest["sha256"] = {"architecture": sha256(HERE / "architecture/config.json"),
                          "detector_config": sha256(folder / "detector_config.json"),
                          "checkpoint": sha256(checkpoint)}
    Path(manifest_path).write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Verify, or with --pin re-pin, a detector bundle")
    parser.add_argument("folder")
    parser.add_argument("--pin", action="store_true")
    args = parser.parse_args()
    print(json.dumps(pin_bundle(args.folder) if args.pin else verify_bundle(args.folder), indent=2))
