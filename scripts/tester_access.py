#!/usr/bin/env python3
"""Issue limited tester access in Actions, or install it using private repository access."""
from __future__ import annotations
import argparse
import base64
import asyncio
import uuid
from datetime import timedelta
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import zipfile

from mac_call_test import CONFIG, private_write, project_host, set_xcconfig

REPO = "shreymp/congressional-app-challenge-2026"
ARTIFACT = "callma-tester-access"
FILENAME = "CallmaTester.json"


def claims(token):
    try:
        if not isinstance(token, str) or len(token) > 16384:
            raise ValueError("Invalid tester connection token")
        value = json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "==="))
        if not isinstance(value, dict):
            raise ValueError("Invalid tester connection token")
        return value
    except (ValueError, IndexError, TypeError):
        raise ValueError("Invalid tester connection token") from None


def validate(config):
    if not isinstance(config, dict) or config.get("schema") != 1:
        raise ValueError("Invalid tester configuration")
    host = project_host(config["host"])
    token = config["lobbyToken"]
    claim = claims(token)
    video = claim.get("video", {})
    expiry = claim.get("exp", 0)
    if not isinstance(video, dict):
        raise ValueError("Invalid tester token grants")
    if (claim.get("sub") != "senior" or video.get("room") != "senior-lobby"
            or video.get("roomJoin") is not True or video.get("canPublish") is not False
            or video.get("canPublishData") is not False or video.get("canSubscribe") is not False):
        raise ValueError("Tester token must be limited to receiving senior-lobby invitations")
    if type(expiry) not in (int, float) or not time.time() + 60 < expiry <= time.time() + 7 * 86400 + 60:
        raise ValueError("Tester access expired or is not short-lived; the owner must renew Tester app access in Actions")
    return host, token, expiry


def issue(output):
    from livekit import api
    host = project_host(os.environ["LIVEKIT_URL"])
    token = (api.AccessToken().with_identity("senior").with_ttl(timedelta(days=7))
             .with_grants(api.VideoGrants(room_join=True, room="senior-lobby", can_publish=False,
                                          can_publish_data=False, can_subscribe=False)).to_jwt())
    config = {"schema": 1, "host": host, "lobbyToken": token}
    validate(config)
    # A compromised/misconfigured signing step must not create an unusable artifact.
    api.TokenVerifier().verify(token)
    private_write(output, json.dumps(config) + "\n")
    print("Created limited app access valid for seven days. No API credentials are in the artifact.")


async def verify_delivery():
    """Verify receive-only data delivery in an isolated room without displacing the app."""
    from livekit import api, rtc
    name = "tester-access-check-" + uuid.uuid4().hex
    identity = "tester-access-check"
    token = (api.AccessToken().with_identity(identity).with_ttl(timedelta(minutes=5))
             .with_grants(api.VideoGrants(room_join=True, room=name, can_publish=False,
                                          can_publish_data=False, can_subscribe=False)).to_jwt())
    room = rtc.Room()
    received = asyncio.Event()
    topic = "callma.tester-access-check"

    @room.on("data_received")
    def receive(packet):
        if packet.topic == topic and packet.data == b"connection-check":
            received.set()

    async with api.LiveKitAPI() as backend:
        try:
            await room.connect(os.environ["LIVEKIT_URL"], token, rtc.RoomOptions(auto_subscribe=False))
            for _ in range(3):
                await backend.room.send_data(api.SendDataRequest(room=name, data=b"connection-check",
                    kind=api.DataPacket.Kind.RELIABLE, destination_identities=[identity], topic=topic))
                try:
                    await asyncio.wait_for(received.wait(), 3)
                    break
                except asyncio.TimeoutError:
                    pass
            if not received.is_set():
                raise RuntimeError("Receive-only app invitation delivery failed")
            print("TESTER ACCESS DELIVERY PASSED: receive-only connection and server data verified")
        finally:
            await room.disconnect()
            try:
                await backend.room.delete_room(api.DeleteRoomRequest(room=name))
            except api.TwirpError as error:
                if error.code != api.TwirpErrorCode.NOT_FOUND:
                    raise


def gh_api(endpoint):
    if not shutil.which("gh"):
        raise RuntimeError("Install GitHub CLI and run gh auth login, or download the Tester app access artifact and use tester --config /path/CallmaTester.json")
    result = subprocess.run(["gh", "api", endpoint], capture_output=True, timeout=90)
    if result.returncode:
        raise RuntimeError("GitHub artifact access failed. Use gh auth login with the account that can read this private repository and its Actions artifacts.")
    return result.stdout


def download():
    metadata = json.loads(gh_api(f"repos/{REPO}/actions/artifacts?name={ARTIFACT}&per_page=30"))
    artifacts = [a for a in metadata["artifacts"] if not a["expired"] and a["name"] == ARTIFACT
                 and a.get("workflow_run", {}).get("head_branch") == "main"]
    if not artifacts:
        raise RuntimeError("No tester access artifact. The owner must run Tester app access on main in GitHub Actions.")
    artifact = max(artifacts, key=lambda a: a["created_at"])
    data = gh_api(f"repos/{REPO}/actions/artifacts/{int(artifact['id'])}/zip")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if archive.getinfo(FILENAME).file_size > 16384:
            raise ValueError("Oversized tester configuration")
        return json.loads(archive.read(FILENAME))


def install(path=None):
    config = json.loads(path.read_text()) if path else download()
    host, token, expiry = validate(config)
    original = CONFIG.read_text() if CONFIG.exists() else "// Private tester connection settings. Do not commit.\n"
    private_write(CONFIG, set_xcconfig(original, {
        "CALLMA_DEMO": "false", "CALLMA_DEFAULT_DIALER": "false",
        "CALLMA_ENTITLEMENTS_FILE": "", "CALLMA_LIVEKIT_HOST": host,
        "CALLMA_LOBBY_TOKEN": token,
    }))
    print("App access installed; expires", time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(expiry)))
    print("Build and run Callma. No LiveKit account, API key, or API secret is needed on this Mac.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("issue"); p.add_argument("--output", type=Path, required=True)
    p = sub.add_parser("install"); p.add_argument("--config", type=Path)
    sub.add_parser("verify")
    args = parser.parse_args()
    try:
        if args.command == "issue":
            issue(args.output)
        elif args.command == "verify":
            asyncio.run(verify_delivery())
        else:
            install(args.config)
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        parser.exit(1, f"{error}\n")
