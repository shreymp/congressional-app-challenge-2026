#!/usr/bin/env python3
"""Mac handoff: setup, configure, doctor, models, services, ring, watch, simulator.

Run from any directory. Secrets are prompted locally and never printed.
"""
from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from urllib.parse import urlparse
import zipfile

ROOT = Path(__file__).resolve().parents[1]
LIVE = ROOT / "backend/AI Deepfake Pipeline/LiveKit Setup"
JEV = ROOT / "backend/Transcript-Based Detector"
VENV = ROOT / ".venv-calltest"
PYTHON = VENV / "bin/python"
CONFIG = ROOT / "ios/Configuration/Local.xcconfig"
ENV = LIVE / ".env.local"
VOSK_NAME = "vosk-model-small-en-us-0.15"
VOSK_SHA = "30f26242c4eb449f948e42cb302dd7a686cb29a3423a8367f99ff41780942498"


def run(args, **kwargs):
    subprocess.run([str(x) for x in args], check=True, cwd=ROOT, **kwargs)


def private_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as output:
        os.fchmod(output.fileno(), 0o600)
        output.write(text)


def set_xcconfig(text, values):
    # Preserve signing/team and unrelated local settings, remove all old active copies.
    lines = [line for line in text.splitlines()
             if line.split("=", 1)[0].strip() not in values]
    for key, value in values.items():
        if any(x in value for x in ("\n", "\r", "//", "$(")):
            raise ValueError("Invalid xcconfig value")
        lines.append(f"{key} = {value}")
    return "\n".join(lines) + "\n"


def project_host(value):
    host = urlparse(value if "://" in value else "wss://" + value)
    if host.scheme != "wss" or not host.hostname or host.username or host.password or host.port or host.path not in ("", "/") or host.query or host.fragment:
        raise ValueError("Use the project's wss:// URL or host, without a path or port")
    if "YOUR" in value.upper():
        raise ValueError("Replace the example host with the actual project URL")
    return host.hostname


def load_environment():
    from dotenv import load_dotenv
    load_dotenv(ENV)


def require_credentials():
    load_environment()
    missing = [key for key in ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET") if not os.environ.get(key)]
    if missing:
        raise RuntimeError("Missing " + ", ".join(missing) + "; run configure --backend")
    project_host(os.environ["LIVEKIT_URL"])


def configure(args):
    if not 0 < args.days <= 7:
        raise ValueError("Token lifetime must be greater than zero and at most 7 days")
    host = project_host(input("LiveKit project WebSocket URL or host: ").strip())
    if args.backend:
        # Keep API secrets on the Mac/backend, never in the iOS build.
        key = getpass.getpass("LiveKit API key: ").strip()
        secret = getpass.getpass("LiveKit API secret: ").strip()
        if not key or not secret or any(c in key + secret for c in "\r\n"):
            raise ValueError("Nonempty, single-line credentials required")
        from dotenv import dotenv_values
        values = dict(dotenv_values(ENV)) if ENV.exists() else dict(dotenv_values(LIVE / ".env.example"))
        values.update(LIVEKIT_URL="wss://" + host, LIVEKIT_API_KEY=key, LIVEKIT_API_SECRET=secret)
        # dotenv accepts JSON-style quoted values for these ordinary string settings.
        private_write(ENV, "".join(f"{k}={json.dumps(v or '')}\n" for k, v in values.items()))
        load_environment()
        # Explicitly use the prompted values even if this shell had older credentials.
        os.environ.update({k: values[k] for k in ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET")})
        sys.path.insert(0, str(LIVE))
        import senior_ring
        token = senior_ring.mint_lobby_token(ttl_days=args.days)
    else:
        token = getpass.getpass("Short-lived lobby token (from project owner): ").strip()
        if len(token.split(".")) != 3:
            raise ValueError("Expected a LiveKit JWT lobby token")
    original = CONFIG.read_text() if CONFIG.exists() else "// Local test settings; do not commit.\n"
    private_write(CONFIG, set_xcconfig(original, {
        "CALLMA_DEMO": "false", "CALLMA_DEFAULT_DIALER": "false",
        "CALLMA_ENTITLEMENTS_FILE": "", "CALLMA_LIVEKIT_HOST": host,
        "CALLMA_LOBBY_TOKEN": token,
    }))
    print("Saved private local configuration. Rebuild the app. No credentials were printed.")


def setup(args):
    if platform.system() != "Darwin":
        raise RuntimeError("Run setup on the MacBook with Xcode 26 installed")
    if sys.version_info < (3, 11):
        raise RuntimeError("Use Python 3.11 or newer")
    run([sys.executable, "-m", "venv", VENV])
    requirements = LIVE / "requirements.txt" if args.local else ROOT / "scripts/requirements-calltest.txt"
    run([PYTHON, "-m", "pip", "install", "-r", requirements])
    if args.local:
        run([PYTHON, "-m", "pip", "install", "-r", JEV / "requirements-model.txt"])
    print("Next: python3 scripts/mac_call_test.py tester (uses GitHub repository access; no LiveKit credentials)")


def download_vosk(destination):
    if (destination / VOSK_NAME / "am/final.mdl").is_file():
        print("Vosk already installed")
        return
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination) as temporary:
        archive = Path(temporary) / "vosk.zip"
        with urllib.request.urlopen(f"https://alphacephei.com/vosk/models/{VOSK_NAME}.zip", timeout=120) as response, archive.open("wb") as output:
            shutil.copyfileobj(response, output)
        with archive.open("rb") as source:
            if hashlib.file_digest(source, "sha256").hexdigest() != VOSK_SHA:
                raise RuntimeError("Vosk checksum mismatch")
        with zipfile.ZipFile(archive) as zipped:
            for member in zipped.infolist():
                if not (Path(temporary) / member.filename).resolve().is_relative_to(Path(temporary).resolve()):
                    raise RuntimeError("Unsafe archive member")
            zipped.extractall(temporary)
        shutil.move(str(Path(temporary) / VOSK_NAME), str(destination / VOSK_NAME))


def models(args):
    download_vosk(LIVE / "models")
    run([PYTHON, ROOT / "ios/scripts/setup_posttrained_jev.py"])
    target = LIVE.parent / "best.pt"
    if args.deepfake_weights:
        source = args.deepfake_weights.expanduser().resolve()
        if not source.is_file():
            raise RuntimeError("Deepfake weights file does not exist")
        if source != target.resolve():
            shutil.copy2(source, target)
    if not target.is_file():
        raise RuntimeError("Vosk/JEV installed. Obtain the trained best.pt from the team and rerun models --deepfake-weights /path/to/best.pt")
    print("Model files present. Run doctor --local to actually load them.")


def request_json(url, data=None):
    payload = None if data is None else json.dumps(data).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.load(response)


def check_services():
    if request_json("http://127.0.0.1:8000/health").get("modelLoaded") is not True:
        raise RuntimeError("JEV model is not loaded")
    if request_json("http://127.0.0.1:3000/health").get("modelConfigured") is not True:
        raise RuntimeError("Connector is not configured")
    score = request_json("http://127.0.0.1:3000/v1/jev/probability", {"transcript": "Caller: Read me the code your bank sent you."}).get("probability")
    if type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 1:
        raise RuntimeError("Connector did not return a finite probability")
    print("JEV model -> connector inference passed")


def doctor(args):
    failures = []
    def check(name, action):
        try:
            action()
            print("PASS:", name)
        except Exception as error:
            failures.append(name)
            # Do not print exceptions that could contain request URLs or credentials.
            print("FAIL:", name, f"({type(error).__name__})")
    def client_config():
        values = dict(line.split("=", 1) for line in CONFIG.read_text().splitlines() if "=" in line and not line.lstrip().startswith("//"))
        values = {k.strip(): v.strip() for k, v in values.items()}
        project_host(values["CALLMA_LIVEKIT_HOST"])
        if values.get("CALLMA_DEMO", "false").lower() != "false":
            raise ValueError("CALLMA_DEMO must be false for live testing")
        import base64
        claims = json.loads(base64.urlsafe_b64decode(values["CALLMA_LOBBY_TOKEN"].split(".")[1] + "==="))
        video = claims.get("video", {})
        load_environment()
        if (claims.get("sub") != (os.environ.get("SENIOR_IDENTITY") or "senior")
                or video.get("room") != (os.environ.get("SENIOR_LOBBY_ROOM") or "senior-lobby")
                or video.get("roomJoin") is not True or video.get("canPublish") is not False):
            raise ValueError("Use a matching senior lobby token, not a call-room token")
        if claims.get("exp", 0) <= time.time():
            raise ValueError("Expired lobby token")
        print("Lobby token expires", time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(claims["exp"])))
    check("Xcode selected", lambda: run(["xcodebuild", "-version"]))
    check("Simulator devices available", lambda: run(["xcrun", "simctl", "list", "devices", "available"]))
    check("App host and unexpired lobby token (local claims only)", client_config)
    if args.backend:
        def cloud():
            require_credentials()
            import asyncio
            from livekit import api
            async def read():
                async with api.LiveKitAPI() as lk:
                    rooms = (await lk.room.list_rooms(api.ListRoomsRequest())).rooms
                    print("Connected to LiveKit; active rooms:", len(rooms))
            asyncio.run(read())
        check("LiveKit backend authentication", cloud)
    if args.local:
        require_credentials()
        sys.path.insert(0, str(LIVE))
        def detector():
            import detector_adapter
            if os.environ.get("DETECTOR", "real") != "real":
                raise ValueError("Use DETECTOR=real for model validation")
            model = detector_adapter.load()
            print("Deepfake warm-up passed on", model.device)
        def stt():
            import transcript_pipeline
            if transcript_pipeline.load_model() is None:
                raise ValueError("Transcription is disabled")
        check("Deepfake weights and inference warm-up", detector)
        check("Vosk model load", stt)
        check("JEV services and real inference", check_services)
    if failures:
        raise RuntimeError("Fix failed checks: " + ", ".join(failures))


def services(args):
    require_credentials()
    if not shutil.which("node"):
        raise RuntimeError("Install Node 22+ first")
    # Refuse occupied ports so an unrelated or stale process cannot satisfy readiness.
    for port in (8000, 3000):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", port))
    children = []
    try:
        children.append(subprocess.Popen([str(PYTHON), str(JEV / "model_service.py")], cwd=ROOT))
        children.append(subprocess.Popen(["node", str(JEV / "server.js")], cwd=JEV,
            env={**os.environ, "JEV_MODEL_URL": "http://127.0.0.1:8000/predict", "PORT": "3000", "HOST": "127.0.0.1"}))
        deadline = time.monotonic() + 180
        while True:
            if any(child.poll() is not None for child in children):
                raise RuntimeError("A service exited; inspect its error above")
            try:
                check_services()
                break
            except (OSError, ValueError, RuntimeError):
                if time.monotonic() >= deadline:
                    raise RuntimeError("Model services did not become ready in 180 seconds")
                time.sleep(1)
        if args.agent:
            children.append(subprocess.Popen([str(PYTHON), "agent.py", "dev"], cwd=LIVE))
        print("Ready. Ctrl+C stops only these child processes.", flush=True)
        while all(child.poll() is None for child in children):
            time.sleep(1)
        raise RuntimeError("A test process exited")
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


def tester(args):
    from tester_access import install
    install(args.config)


def cloud_probe(args):
    require_credentials()
    fixture = args.wav or ROOT / "ios/ScamTranscriptTests/Fixtures/bank.wav"
    command = [PYTHON, ROOT / "deploy/livekit/probe.py", fixture,
               "--timeout", str(args.timeout), "--attempts", "1"]
    if args.command == "full-call":
        command.append("--ring")
    run(command)


def simulator(args):
    if not CONFIG.is_file():
        raise RuntimeError("Run configure first")
    run(["xcrun", "simctl", "bootstatus", args.device, "-b"])
    run(["xcodebuild", "-project", "ios/Callma.xcodeproj", "-scheme", "Callma", "-configuration", "Debug",
         "-destination", f"platform=iOS Simulator,id={args.device}", "-derivedDataPath", "ios/build-calltest", "CODE_SIGNING_ALLOWED=NO", "build"])
    app = ROOT / "ios/build-calltest/Build/Products/Debug-iphonesimulator/Callma.app"
    result = subprocess.run(["/usr/libexec/PlistBuddy", "-c", "Print CFBundleIdentifier", str(app / "Info.plist")], capture_output=True, text=True, check=True)
    run(["xcrun", "simctl", "install", args.device, app])
    run(["open", "-a", "Simulator"])
    run(["xcrun", "simctl", "launch", args.device, result.stdout.strip()])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("setup"); p.add_argument("--local", action="store_true"); p.set_defaults(func=setup)
    p = sub.add_parser("tester", help="install limited app access using GitHub; no LiveKit credentials"); p.add_argument("--config", type=Path); p.set_defaults(func=tester)
    p = sub.add_parser("configure"); p.add_argument("--backend", action="store_true"); p.add_argument("--days", type=float, default=1); p.set_defaults(func=configure)
    p = sub.add_parser("models"); p.add_argument("--deepfake-weights", type=Path); p.set_defaults(func=models)
    p = sub.add_parser("doctor"); p.add_argument("--backend", action="store_true"); p.add_argument("--local", action="store_true"); p.set_defaults(func=doctor)
    p = sub.add_parser("services"); p.add_argument("--agent", action="store_true", help="Only after the cloud worker is stopped; never run duplicate scam-guard workers"); p.set_defaults(func=services)
    p = sub.add_parser("simulator"); p.add_argument("--device", required=True, help="Simulator UDID from xcrun simctl list devices available"); p.set_defaults(func=simulator)
    for command in ("cloud-probe", "full-call"):
        p = sub.add_parser(command, help="test both hosted models" + (" and the simulator call" if command == "full-call" else " without an app"))
        p.add_argument("--wav", type=Path, help="consented speech WAV; defaults to the included synthetic bank fixture")
        p.add_argument("--timeout", type=float, default=180)
        p.set_defaults(func=cloud_probe)
    for command, tool in (("ring", "test_ring.py"), ("watch", "watch_risk.py")):
        p = sub.add_parser(command)
        p.set_defaults(func=lambda a, tool=tool: (require_credentials(), run([PYTHON, LIVE / "tools" / tool, *a.args])))
    args, passthrough = parser.parse_known_args()
    if args.command not in ("ring", "watch") and passthrough:
        parser.error("unrecognized arguments: " + " ".join(passthrough))
    args.args = passthrough
    if sys.version_info < (3, 11):
        parser.error("Python 3.11+ required")
    if args.command != "setup" and not PYTHON.exists():
        parser.error("Run python3 scripts/mac_call_test.py setup first")
    if args.command != "setup" and PYTHON.exists() and Path(sys.prefix).resolve() != VENV.resolve():
        os.execv(str(PYTHON), [str(PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]])
    try:
        args.func(args)
    except KeyboardInterrupt:
        print("Stopped")
    except (RuntimeError, ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()

