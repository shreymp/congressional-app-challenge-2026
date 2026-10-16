"""Build-stage downloads. Inputs contain short-lived asset URLs, never GitHub keys."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import urllib.request
import zipfile


def download(sources, destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    for item in sources:
        target = destination / item["path"]
        if not target.resolve().is_relative_to(destination.resolve()):
            raise ValueError("Invalid model destination")
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_suffix(target.suffix + ".partial")
        try:
            # Do not print URLs: private release redirects are short-lived bearer links.
            with urllib.request.urlopen(item["url"], timeout=180) as source, partial.open("wb") as output:
                shutil.copyfileobj(source, output)
            with partial.open("rb") as source:
                digest = hashlib.file_digest(source, "sha256").hexdigest()
            if digest != item["sha256"]:
                raise ValueError("Model checksum mismatch: " + item["path"])
            partial.replace(target)
            if item.get("extract"):
                with zipfile.ZipFile(target) as archive:
                    for member in archive.infolist():
                        if not (destination / member.filename).resolve().is_relative_to(destination.resolve()):
                            raise ValueError("Unsafe model archive")
                    archive.extractall(destination)
                target.unlink()
            print("Verified model asset:", item["path"], flush=True)
        finally:
            partial.unlink(missing_ok=True)


if __name__ == "__main__":
    download(json.loads(Path(sys.argv[1]).read_text()), Path(sys.argv[2]))
