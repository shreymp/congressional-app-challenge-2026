"""Offline tests for drive_upload (HTTP is mocked; no network, no credentials)."""
import base64
import io
import json
import os
import tempfile
import unittest
import urllib.error
import wave
from unittest import mock

import drive_upload

ENV = {"GDRIVE_UPLOAD_URL": "https://script.example/exec", "GDRIVE_UPLOAD_TOKEN": "s3cret-token"}
RATE = 16000


def make_wav(seconds):
    handle = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    handle.close()
    with wave.open(handle.name, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(b"\x01\x00" * int(RATE * seconds))
    return handle.name


class Reply(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def ok(file_id="f"):
    return Reply(json.dumps({"ok": True, "id": file_id}).encode())


class DriveUploadTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, ENV)
        patcher.start()
        self.addCleanup(patcher.stop)
        sleeper = mock.patch.object(drive_upload.time, "sleep")
        sleeper.start()
        self.addCleanup(sleeper.stop)

    def wav(self, seconds):
        path = make_wav(seconds)
        self.addCleanup(os.unlink, path)
        return path

    def test_skipped_without_credentials(self):
        with mock.patch.dict(os.environ, {"GDRIVE_UPLOAD_TOKEN": ""}), \
                mock.patch.object(drive_upload.urllib.request, "urlopen") as urlopen:
            self.assertFalse(drive_upload.configured())
            self.assertEqual(drive_upload.upload_with_retry(self.wav(1)), 0)
            urlopen.assert_not_called()

    def test_short_call_is_one_valid_wav_with_token_in_body_only(self):
        sent = []

        def fake(request, timeout=None):
            sent.append(request)
            return ok()

        path = self.wav(3)
        with mock.patch.object(drive_upload.urllib.request, "urlopen", fake):
            self.assertEqual(drive_upload.upload_with_retry(path), 1)
        (request,) = sent
        self.assertNotIn("s3cret-token", request.full_url)
        body = json.loads(request.data)
        self.assertEqual(body["token"], "s3cret-token")
        self.assertEqual(body["name"], os.path.basename(path))
        with wave.open(io.BytesIO(base64.b64decode(body["data"]))) as piece:
            self.assertEqual(piece.getnframes(), 3 * RATE)

    def test_long_call_is_split_into_numbered_valid_pieces(self):
        names, frames = [], []

        def fake(request, timeout=None):
            body = json.loads(request.data)
            names.append(body["name"])
            with wave.open(io.BytesIO(base64.b64decode(body["data"]))) as piece:
                frames.append(piece.getnframes())
            return ok()

        with mock.patch.object(drive_upload.urllib.request, "urlopen", fake):
            self.assertEqual(drive_upload.upload_with_retry(self.wav(150)), 3)
        self.assertEqual([n.rsplit("_part", 1)[1] for n in names], ["01.wav", "02.wav", "03.wav"])
        self.assertEqual(frames, [60 * RATE, 60 * RATE, 30 * RATE])

    def test_retries_then_succeeds(self):
        calls = iter([urllib.error.URLError("boom"), ok()])

        def fake(request, timeout=None):
            result = next(calls)
            if isinstance(result, Exception):
                raise result
            return result

        with mock.patch.object(drive_upload.urllib.request, "urlopen", fake):
            self.assertEqual(drive_upload.upload_with_retry(self.wav(2)), 1)

    def test_rejection_and_http_errors_never_raise_or_leak_the_token(self):
        rejected = Reply(json.dumps({"ok": False, "error": "unauthorized"}).encode())
        http = urllib.error.HTTPError("u", 500, "err", {}, io.BytesIO(b"s3cret-token"))
        for failure in (rejected, http):
            with mock.patch.object(drive_upload.urllib.request, "urlopen",
                                   side_effect=lambda r, timeout=None, f=failure: f if f is rejected else (_ for _ in ()).throw(f)), \
                    self.assertLogs("scam-guard.drive", "WARNING") as logs:
                self.assertEqual(drive_upload.upload_with_retry(self.wav(2)), 0)
            self.assertNotIn("s3cret-token", "\n".join(logs.output))
            rejected.seek(0)


if __name__ == "__main__":
    unittest.main()
