#!/usr/bin/env python3
"""Download and bundle the exact experimental post-trained call classifiers."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as source:
        while chunk := source.read(1024 * 1024):
            result.update(chunk)
    return result.hexdigest()


def main():
    manifest = json.loads((ROOT / 'backend/jev-posttrain/model_downloads.json').read_text())
    for checkpoint in manifest:
        source = ROOT / 'backend/jev-posttrain/runs' / checkpoint['run']
        destination = ROOT / 'ios/ScamTranscript/Resources' / ('JevCall' + checkpoint['version'])
        destination.mkdir(parents=True, exist_ok=True)
        for name, asset in checkpoint['files'].items():
            target = destination / name
            if target.is_file() and digest(target) == asset['sha256']:
                print(f'Already verified: {target}')
                continue
            local = source / name
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(dir=destination, prefix='.jev-', delete=False) as output:
                    temporary = Path(output.name)
                    if local.is_file() and digest(local) == asset['sha256']:
                        with local.open('rb') as input_file:
                            shutil.copyfileobj(input_file, output)
                    else:
                        print(f'Downloading {checkpoint["version"]}/{name}', flush=True)
                        with urllib.request.urlopen(asset['url'], timeout=120) as response:
                            shutil.copyfileobj(response, output)
                if digest(temporary) != asset['sha256']:
                    raise RuntimeError(f'Checksum mismatch: {name}')
                os.replace(temporary, target)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
            print(f'Bundled and verified: {target}')


if __name__ == '__main__':
    main()
