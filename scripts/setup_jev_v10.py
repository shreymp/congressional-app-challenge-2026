#!/usr/bin/env python3
"""Install the exact published V10 bundle. Standard library; never unpickle weights."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'backend/jev-posttrain/v10_release.json'
DEFAULT_DESTINATION = ROOT / 'backend/jev-posttrain/runs/call-v10-github'


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is not None:
            redirected.remove_header('Authorization')
        return redirected


def github_token():
    token = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
    if token:
        return token
    for command, data in [(['gh', 'auth', 'token'], None),
                          (['git', 'credential', 'fill'], 'protocol=https\nhost=github.com\n\n')]:
        try:
            result = subprocess.run(command, input=data, text=True, capture_output=True,
                                    timeout=15, env={**os.environ, 'GIT_TERMINAL_PROMPT': '0'})
            if result.returncode == 0:
                if data is None:
                    return result.stdout.strip()
                fields = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
                return fields.get('password')
        except (OSError, subprocess.TimeoutExpired):
            pass
    return None


def download(release, target):
    token = github_token()
    headers = {'User-Agent': 'JEV-V10-setup', 'Accept': 'application/vnd.github+json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    opener = urllib.request.build_opener(SafeRedirect())
    api = 'https://api.github.com/repos/' + release['repository']
    try:
        with opener.open(urllib.request.Request(api + '/releases/tags/' + release['tag'], headers=headers), timeout=60) as source:
            metadata = json.load(source)
        asset = next(a for a in metadata['assets'] if a['name'] == release['asset'])
        headers['Accept'] = 'application/octet-stream'
        url = asset['url'] if token else asset['browser_download_url']
        print('Downloading V10 (about 1.1 GB); please wait.', flush=True)
        with opener.open(urllib.request.Request(url, headers=headers), timeout=120) as source, target.open('wb') as output:
            shutil.copyfileobj(source, output)
    except urllib.error.HTTPError as error:
        if error.code in (401, 403, 404):
            raise RuntimeError('GitHub repository read access is required. Use your existing gh/Git login or set GH_TOKEN. Alternatively download the release ZIP in your browser and pass --archive PATH.') from None
        raise


def verify(directory, release):
    for name, info in release['bundle']['files'].items():
        path = directory / name
        if not path.is_file() or path.stat().st_size != info['bytes'] or digest(path) != info['sha256']:
            raise RuntimeError('Missing or mismatched V10 file: ' + name)


def install(release, destination, archive=None):
    if destination.exists():
        verify(destination, release)
        print('Already installed and verified:', destination)
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.jev-v10-', dir=destination.parent) as temporary:
        work = Path(temporary)
        package = Path(archive).expanduser() if archive else work / release['asset']
        if archive is None:
            download(release, package)
        if package.stat().st_size != release['bytes'] or digest(package) != release['sha256']:
            raise RuntimeError('V10 archive checksum mismatch; no installed files changed.')
        staged = work / 'model'
        staged.mkdir()
        allowed = set(release['bundle']['files']) | {'bundle.json'}
        with zipfile.ZipFile(package) as bundle:
            names = bundle.namelist()
            if set(names) != allowed or len(names) != len(allowed):
                raise RuntimeError('Unexpected files in V10 archive')
            for name, info in release['bundle']['files'].items():
                if bundle.getinfo(name).file_size != info['bytes']:
                    raise RuntimeError('Unexpected uncompressed file size: ' + name)
            for name in names:
                if Path(name).name != name:
                    raise RuntimeError('Unsafe archive member')
                with bundle.open(name) as source, (staged / name).open('wb') as output:
                    shutil.copyfileobj(source, output)
        verify(staged, release)
        os.rename(staged, destination)
    print('Installed and verified V10:', destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, help='Use a browser-downloaded ZIP instead of downloading')
    parser.add_argument('--destination', type=Path, default=DEFAULT_DESTINATION)
    args = parser.parse_args()
    try:
        install(json.loads(MANIFEST.read_text()), args.destination.resolve(), args.archive)
    except (OSError, RuntimeError, ValueError, StopIteration, zipfile.BadZipFile) as error:
        parser.exit(1, f'V10 installation failed: {error}\n')


if __name__ == '__main__':
    main()
