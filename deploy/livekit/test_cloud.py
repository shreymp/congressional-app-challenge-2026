import importlib.util
import json
from pathlib import Path
import struct
import threading
import unittest
import urllib.error
import urllib.request

spec = importlib.util.spec_from_file_location("model_server", Path(__file__).with_name("model_server.py"))
model_server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model_server)


class Voice:
    device = "cpu"
    meta = {"window_sec": 4, "sample_rate": 16000, "threshold_eer": .9, "threshold_1pct_fpr": .99}
    def score_window(self, audio):
        return {"p_fake": .75, "logit": 1.1, "infer_ms": 2}


class Text:
    def score(self, transcript):
        return .9


class CloudTests(unittest.TestCase):
    def setUp(self):
        self.server = model_server.make_server(Voice(), Text(), 0)
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        self.url = "http://127.0.0.1:" + str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, path, body=None):
        request = urllib.request.Request(self.url + path, data=body)
        with urllib.request.urlopen(request) as response:
            return json.load(response)

    def test_both_real_service_contracts(self):
        health = self.request("/health")
        self.assertTrue(health["deepfakeLoaded"])
        self.assertEqual(health["mode"], "real")
        self.assertEqual(self.request("/predict", b'{"transcript":"Caller: a test"}')["probability"], .9)
        self.assertEqual(self.request("/deepfake", struct.pack("<4f", .1, -.1, .2, -.2))["p_fake"], .75)

    def test_invalid_pcm_or_transcripts_never_reach_inference(self):
        for path, body in (("/deepfake", b"abc"), ("/deepfake", struct.pack("<f", float("nan"))),
                           ("/predict", b'{"transcript":""}'), ("/predict", b"[]")):
            with self.assertRaises(urllib.error.HTTPError) as raised:
                self.request(path, body)
            self.assertEqual(raised.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
