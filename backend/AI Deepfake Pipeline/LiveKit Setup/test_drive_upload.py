"""Offline tests for drive_upload (HTTP is mocked; no network, no credentials)."""
import io
import json
import os
import tempfile
import unittest
import urllib.error
from unittest import mock

import drive_upload

ENV = {"GDRIVE_CLIENT_ID": "id", "GDRIVE_CLIENT_SECRET": "secret", "GDRIVE_REFRESH_TOKEN": "refresh"}


class Reply(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def reply(obj):
    return Reply(json.dumps(obj).encode())


class DriveUploadTests(unittest.TestCase):
    def setUp(self):
        drive_upload._folder_id = None
        self.wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        self.wav.write(b"RIFFfakewavdata")
        self.wav.close()
        self.addCleanup(os.unlink, self.wav.name)
        patcher = mock.patch.dict(os.environ, ENV)
        patcher.start()
        self.addCleanup(patcher.stop)
        sleeper = mock.patch.object(drive_upload.time, "sleep")
        sleeper.start()
        self.addCleanup(sleeper.stop)

    def test_skipped_without_credentials(self):
        with mock.patch.dict(os.environ, {"GDRIVE_REFRESH_TOKEN": ""}), \
                mock.patch.object(drive_upload.urllib.request, "urlopen") as urlopen:
            self.assertFalse(drive_upload.configured())
            self.assertIsNone(drive_upload.upload_with_retry(self.wav.name))
            urlopen.assert_not_called()

    def test_creates_folder_then_uploads_into_it(self):
        replies = [reply({"access_token": "tok"}), reply({"files": []}),
                   reply({"id": "folder1"}), reply({"id": "file1"})]
        requests = []

        def fake(request, timeout=None):
            requests.append(request)
            return replies.pop(0)

        with mock.patch.object(drive_upload.urllib.request, "urlopen", fake):
            self.assertEqual(drive_upload.upload_with_retry(self.wav.name), "file1")
        token, find, create, upload = requests
        self.assertIn(b"grant_type=refresh_token", token.data)
        self.assertEqual(find.get_header("Authorization"), "Bearer tok")
        self.assertEqual(json.loads(create.data)["mimeType"], drive_upload.FOLDER_MIME)
        self.assertIn(b'"parents": ["folder1"]', upload.data)
        self.assertIn(b"RIFFfakewavdata", upload.data)
        self.assertTrue(upload.get_header("Content-type").startswith("multipart/related; boundary="))

    def test_reuses_existing_folder_and_caches_it(self):
        replies = [reply({"access_token": "t"}), reply({"files": [{"id": "old"}]}), reply({"id": "a"}),
                   reply({"access_token": "t"}), reply({"id": "b"})]
        with mock.patch.object(drive_upload.urllib.request, "urlopen", lambda r, timeout=None: replies.pop(0)):
            self.assertEqual(drive_upload.upload_with_retry(self.wav.name), "a")
            self.assertEqual(drive_upload.upload_with_retry(self.wav.name), "b")
        self.assertEqual(replies, [])

    def test_failure_returns_none_and_never_raises(self):
        err = urllib.error.HTTPError("u", 403, "forbidden", {}, io.BytesIO(b"secret-in-body"))
        with mock.patch.object(drive_upload.urllib.request, "urlopen", side_effect=err), \
                self.assertLogs("scam-guard.drive", "WARNING") as logs:
            self.assertIsNone(drive_upload.upload_with_retry(self.wav.name))
        self.assertNotIn("secret-in-body", "\n".join(logs.output))
        self.assertNotIn("refresh", "\n".join(logs.output))


if __name__ == "__main__":
    unittest.main()
