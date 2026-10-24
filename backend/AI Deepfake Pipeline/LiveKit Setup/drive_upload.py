"""Send saved caller audio to Google Drive through an Apps Script web app (stdlib only).

The cloud worker has no Google login of its own, so it POSTs each recording to a small
Apps Script web app that runs as the Drive owner and saves the file into a Drive folder
("CAC call recordings"). The web app only accepts requests carrying the shared secret.

A call is cut into SEGMENT_SEC pieces, each a standalone, valid WAV (<name>_part01.wav,
<name>_part02.wav, ...). Google does not document a limit on incoming request size, so the
pieces are kept small (about 2 MB each) rather than relying on one big request.

Environment (both required, otherwise uploading is skipped):
  GDRIVE_UPLOAD_URL    the web app's /exec URL
  GDRIVE_UPLOAD_TOKEN  shared secret, sent in the request body (never in the URL)
"""
from __future__ import annotations

import base64
import io
import json
import logging
import os
import time
import urllib.error
import urllib.request
import wave

log = logging.getLogger("scam-guard.drive")

SEGMENT_SEC = 60
ATTEMPTS = 3


def configured() -> bool:
    return bool(os.environ.get("GDRIVE_UPLOAD_URL") and os.environ.get("GDRIVE_UPLOAD_TOKEN"))


def segments(path: str, segment_sec: int = SEGMENT_SEC):
    """Yield (suffix, wav_bytes) pieces of a PCM WAV file; each piece is a valid WAV."""
    with wave.open(path, "rb") as src:
        params = src.getparams()
        per_segment = max(1, int(segment_sec * src.getframerate()))
        pieces = []
        while True:
            frames = src.readframes(per_segment)
            if not frames:
                break
            buffer = io.BytesIO()
            with wave.open(buffer, "wb") as dst:
                dst.setnchannels(params.nchannels)
                dst.setsampwidth(params.sampwidth)
                dst.setframerate(params.framerate)
                dst.writeframes(frames)
            pieces.append(buffer.getvalue())
    if len(pieces) == 1:
        yield "", pieces[0]
        return
    for number, data in enumerate(pieces, 1):
        yield f"_part{number:02d}", data


def _post(name: str, data: bytes) -> str:
    body = json.dumps({"token": os.environ["GDRIVE_UPLOAD_TOKEN"], "name": name,
                       "data": base64.b64encode(data).decode("ascii")}).encode()
    request = urllib.request.Request(os.environ["GDRIVE_UPLOAD_URL"], data=body, method="POST",
                                     headers={"Content-Type": "text/plain;charset=utf-8"})
    # Apps Script answers a POST with a 302 to the result page; urllib follows it with a GET.
    with urllib.request.urlopen(request, timeout=120) as response:
        reply = json.load(response)
    if not reply.get("ok"):
        raise RuntimeError("upload rejected: " + str(reply.get("error", "unknown"))[:80])
    return str(reply.get("id", ""))


def upload_with_retry(path: str) -> int:
    """Best-effort upload used by the agent. Never raises; returns how many pieces were uploaded."""
    if not configured():
        log.info("Drive upload skipped: GDRIVE_UPLOAD_URL / GDRIVE_UPLOAD_TOKEN are not set")
        return 0
    stem, ext = os.path.splitext(os.path.basename(path))
    uploaded = 0
    try:
        pieces = list(segments(path))
    except Exception as error:
        log.error("could not read %s for upload: %s", os.path.basename(path), type(error).__name__)
        return 0
    for suffix, data in pieces:
        name = f"{stem}{suffix}{ext}"
        for attempt in range(1, ATTEMPTS + 1):
            try:
                file_id = _post(name, data)
                uploaded += 1
                log.info("uploaded %s to Google Drive (file id %s)", name, file_id)
                break
            except urllib.error.HTTPError as error:
                # Never log response bodies or headers: they can echo credentials.
                log.warning("Drive upload %s attempt %d/%d failed: HTTP %s", name, attempt, ATTEMPTS, error.code)
            except Exception as error:  # network hiccup, rejected token, malformed reply
                log.warning("Drive upload %s attempt %d/%d failed: %s: %s", name, attempt, ATTEMPTS,
                            type(error).__name__, str(error)[:80] if isinstance(error, RuntimeError) else "")
            if attempt < ATTEMPTS:
                time.sleep(2 * attempt)
        else:
            log.error("Drive upload gave up on %s; the local file was kept", name)
    return uploaded
