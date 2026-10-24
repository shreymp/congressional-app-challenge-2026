"""Upload saved caller audio to Google Drive (stdlib only, OAuth refresh token).

Why a refresh token and not a service account: a service account has no Drive storage of
its own and cannot save files into a normal personal My Drive folder. This uploads as the
Drive owner instead, using the narrow ``drive.file`` scope, which only lets the app touch
files and folders it created itself. The first upload creates the folder (default name
"CAC call recordings") and later uploads find it again by name.

Environment (all three are required, otherwise uploading is skipped):
  GDRIVE_CLIENT_ID, GDRIVE_CLIENT_SECRET, GDRIVE_REFRESH_TOKEN
Optional:
  GDRIVE_FOLDER_NAME   folder created/used in the owner's My Drive
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

log = logging.getLogger("scam-guard.drive")

TOKEN_URL = "https://oauth2.googleapis.com/token"
FILES_URL = "https://www.googleapis.com/drive/v3/files"
UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart"
FOLDER_MIME = "application/vnd.google-apps.folder"
ATTEMPTS = 3

_folder_lock = threading.Lock()
_folder_id: str | None = None


def configured() -> bool:
    return all(os.environ.get(k) for k in ("GDRIVE_CLIENT_ID", "GDRIVE_CLIENT_SECRET", "GDRIVE_REFRESH_TOKEN"))


def _folder_name() -> str:
    return os.environ.get("GDRIVE_FOLDER_NAME") or "CAC call recordings"


def _open(request: urllib.request.Request, timeout: float = 60) -> dict:
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def _access_token() -> str:
    body = urllib.parse.urlencode({
        "client_id": os.environ["GDRIVE_CLIENT_ID"],
        "client_secret": os.environ["GDRIVE_CLIENT_SECRET"],
        "refresh_token": os.environ["GDRIVE_REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    }).encode()
    request = urllib.request.Request(TOKEN_URL, data=body, method="POST",
                                     headers={"Content-Type": "application/x-www-form-urlencoded"})
    return _open(request, timeout=30)["access_token"]


def _auth(token: str, **extra: str) -> dict:
    return {"Authorization": "Bearer " + token, **extra}


def _ensure_folder(token: str) -> str:
    global _folder_id
    with _folder_lock:
        if _folder_id:
            return _folder_id
        name = _folder_name().replace("\\", "\\\\").replace("'", "\\'")
        query = f"name = '{name}' and mimeType = '{FOLDER_MIME}' and trashed = false"
        url = FILES_URL + "?" + urllib.parse.urlencode({"q": query, "fields": "files(id,name)", "pageSize": "1"})
        found = _open(urllib.request.Request(url, headers=_auth(token)), timeout=30).get("files", [])
        if found:
            _folder_id = found[0]["id"]
        else:
            body = json.dumps({"name": _folder_name(), "mimeType": FOLDER_MIME}).encode()
            request = urllib.request.Request(FILES_URL + "?fields=id", data=body, method="POST",
                                             headers=_auth(token, **{"Content-Type": "application/json"}))
            _folder_id = _open(request, timeout=30)["id"]
            log.info("created Drive folder %r", _folder_name())
        return _folder_id


def _multipart(metadata: dict, data: bytes, mime: str) -> tuple[bytes, str]:
    boundary = "cac" + uuid.uuid4().hex
    head = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
            f"{json.dumps(metadata)}\r\n--{boundary}\r\nContent-Type: {mime}\r\n\r\n").encode()
    return head + data + f"\r\n--{boundary}--".encode(), boundary


def upload_file(path: str, mime: str = "audio/wav") -> str:
    """Upload ``path`` to the Drive folder and return the new file's id. Raises on failure."""
    token = _access_token()
    parent = _ensure_folder(token)
    with open(path, "rb") as handle:
        data = handle.read()
    body, boundary = _multipart({"name": os.path.basename(path), "parents": [parent]}, data, mime)
    request = urllib.request.Request(
        UPLOAD_URL + "&fields=id", data=body, method="POST",
        headers=_auth(token, **{"Content-Type": f"multipart/related; boundary={boundary}"}))
    return _open(request, timeout=120)["id"]


def upload_with_retry(path: str) -> str | None:
    """Best-effort upload used by the agent. Never raises; returns the file id or None."""
    if not configured():
        log.info("Drive upload skipped: GDRIVE_* credentials are not set")
        return None
    for attempt in range(1, ATTEMPTS + 1):
        try:
            file_id = upload_file(path)
            log.info("uploaded %s to Google Drive (file id %s)", os.path.basename(path), file_id)
            return file_id
        except urllib.error.HTTPError as error:
            # Never log the response body or headers: they can echo credentials.
            log.warning("Drive upload attempt %d/%d failed: HTTP %s", attempt, ATTEMPTS, error.code)
            if error.code in (400, 401, 403) and attempt >= 2:
                break
        except Exception as error:  # network hiccup, bad file, malformed reply
            log.warning("Drive upload attempt %d/%d failed: %s", attempt, ATTEMPTS, type(error).__name__)
        if attempt < ATTEMPTS:
            time.sleep(2 * attempt)
    log.error("Drive upload gave up for %s; the local file was kept", os.path.basename(path))
    return None
