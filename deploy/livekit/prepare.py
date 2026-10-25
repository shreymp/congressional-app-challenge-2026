"""Create a small cloud build context using authenticated, expiring release URLs."""
import argparse
import json
import os
from pathlib import Path
import shutil
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
REPO = "shreymp/congressional-app-challenge-2026"
# V8b checkpoint; the previous V2 best.pt was release asset 628783673.
DETECTOR_RELEASE_TAG = "deepfake-weights-v8"
DETECTOR_ASSET_NAME = "detector_state_v8b.pt"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def asset_url(api_url, token):
    request = urllib.request.Request(api_url, headers={
        "Authorization": "Bearer " + token, "Accept": "application/octet-stream",
        "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "CAC-cloud-build"})
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=30):
            raise RuntimeError("Expected a private release asset redirect")
    except urllib.error.HTTPError as error:
        if error.code not in (301, 302, 303, 307, 308):
            raise RuntimeError(f"GitHub model access failed ({error.code})") from None
        location = error.headers["Location"]
        if not location.startswith("https://"):
            raise RuntimeError("Model redirect must use HTTPS")
        return location


def release_asset_api_url(tag, name, token):
    request = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/tags/{tag}", headers={
        "Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "CAC-cloud-build"})
    with urllib.request.urlopen(request, timeout=30) as response:
        assets = json.load(response)["assets"]
    match = [a for a in assets if a["name"] == name]
    if len(match) != 1:
        raise RuntimeError(f"Release {tag} must contain exactly one asset named {name}")
    return match[0]["url"]


def prepare(output):
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("A read-only repository token is required to resolve private model assets")
    output = output.resolve()
    if output == ROOT or output.exists():
        raise RuntimeError("Choose a new output directory")
    output.mkdir(parents=True)
    for folder in ("backend/AI Deepfake Pipeline", "backend/Transcript-Based Detector"):
        shutil.copytree(ROOT / folder, output / folder,
                        ignore=shutil.ignore_patterns("best.pt", "*.wav", "logs", "models", "recordings", "node_modules", ".env*", "__pycache__", "test*", ".venv*"))
    manifest_path = Path("backend/jev-posttrain/model_downloads.json")
    (output / manifest_path).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / manifest_path, output / manifest_path)
    shutil.copytree(ROOT / "deploy/livekit", output / "deploy/livekit", ignore=shutil.ignore_patterns("__pycache__", "test*"))
    shutil.copy2(ROOT / "deploy/livekit/Dockerfile", output / "Dockerfile")
    shutil.copy2(ROOT / "deploy/livekit/livekit.toml", output / "livekit.toml")
    # `lk agent deploy` detects the project type from a requirements.txt at the context root.
    # The Dockerfile still installs from deploy/livekit/requirements.txt; this copy is for detection.
    shutil.copy2(ROOT / "deploy/livekit/requirements.txt", output / "requirements.txt")
    sources = [{"path": "deepfake/detector_state.pt", "sha256": "cc6a75eae2948aeae5f491dffbc0e05af274bb4d8f6740451ad762b72f9703d5",
                "url": asset_url(release_asset_api_url(DETECTOR_RELEASE_TAG, DETECTOR_ASSET_NAME, token), token)}]
    bundle = next(b for b in json.loads((ROOT / manifest_path).read_text()) if b["version"] == "V2")
    for name, item in bundle["files"].items():
        sources.append({"path": "JevCallV2/" + name, "sha256": item["sha256"], "url": asset_url(item["api_url"], token)})
    sources.append({"path": "vosk.zip", "extract": True,
                    "url": "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip",
                    "sha256": "30f26242c4eb449f948e42cb302dd7a686cb29a3423a8367f99ff41780942498"})
    # Keep architecture thresholds alongside the released state dict.
    config = output / "models/deepfake/detector_config.json"
    config.parent.mkdir(parents=True)
    shutil.copy2(ROOT / "backend/AI Deepfake Pipeline/detector_config.json", config)
    # Docker's models stage needs this small non-secret config too.
    docker = (output / "Dockerfile").read_text().replace("COPY model-sources.json ./", "COPY model-sources.json ./\nCOPY models/deepfake/detector_config.json /models/deepfake/detector_config.json")
    (output / "Dockerfile").write_text(docker)
    descriptor = output / "model-sources.json"
    descriptor.write_text(json.dumps(sources))
    descriptor.chmod(0o600)
    print("Prepared cloud build context; private model URLs expire and are used only by the build stage")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    prepare(parser.parse_args().output)
