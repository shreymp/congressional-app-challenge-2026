#!/usr/bin/env python3
"""Download and bundle the exact experimental post-trained call classifiers."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import urllib.error
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as source:
        while chunk := source.read(1024 * 1024):
            result.update(chunk)
    return result.hexdigest()


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is not None:
            redirected.remove_header('Authorization')
        return redirected


def download(asset):
    token = os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN')
    if not token:
        try:
            result = subprocess.run(
                ['git', 'credential', 'fill'],
                input='protocol=https\nhost=github.com\n\n',
                text=True, capture_output=True, timeout=15,
                env={**os.environ, 'GIT_TERMINAL_PROMPT': '0'},
            )
            fields = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
            token = fields.get('password')
        except (OSError, subprocess.TimeoutExpired):
            pass
    headers = {'User-Agent': 'CAC-model-setup'}
    url = asset['url']
    if token:
        url = asset['api_url']
        headers.update({'Authorization': 'Bearer ' + token, 'Accept': 'application/octet-stream'})
    try:
        return urllib.request.build_opener(SafeRedirect()).open(
            urllib.request.Request(url, headers=headers), timeout=120)
    except urllib.error.HTTPError as error:
        if error.code in (401, 403, 404):
            raise RuntimeError('Model download requires GitHub repository access. Configure Git HTTPS credentials or set GITHUB_TOKEN to a token with read access to this private repository.') from None
        raise


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
                        with download(asset) as response:
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
