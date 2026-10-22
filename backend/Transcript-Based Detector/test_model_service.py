"""Standard-library tests, including the REAL Node connector with a fake model only."""
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request

from model_service import calibrated_probability, make_server, render_prompt

HERE = Path(__file__).resolve().parent
PIPELINE = HERE.parent / "AI Deepfake Pipeline/LiveKit Setup/transcript_pipeline.py"
spec = importlib.util.spec_from_file_location("transcript_pipeline_test", PIPELINE)
pipeline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pipeline)


class FakeModel:
    def __init__(self):
        self.received = []
        self.fail = False

    def score(self, text):
        self.received.append(text)
        if self.fail:
            raise RuntimeError("fake model offline")
        return 0.91


class ModelServiceTests(unittest.TestCase):
    def test_calibration_and_prompt_match_training_contract(self):
        self.assertAlmostEqual(calibrated_probability(3, 1, 2), 1 / (1 + math.exp(-1)))
        self.assertEqual(calibrated_probability(10000, -10000, 1), 1)
        self.assertEqual(calibrated_probability(-10000, 10000, 1), 0)
        for temperature in (0, -1, float("nan")):
            with self.assertRaises(ValueError):
                calibrated_probability(1, 2, temperature)
        prompt = render_prompt("Caller: read me the code")
        self.assertTrue(prompt.startswith("<<LABEL>>true: The caller"))
        self.assertIn("<<SEP>>Context:\nCaller: read me the code", prompt)
        self.assertEqual(prompt.count("<<LABEL>>"), 3)

    @unittest.skipUnless(shutil.which("node"), "Node is required for the connector integration")
    def test_pipeline_http_through_node_connector_to_model_service(self):
        model = FakeModel()
        server = make_server(model, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        # Let Node bind an ephemeral port and announce it. No test port collisions.
        script = ("const {app}=require('./server');app.listen(0,'127.0.0.1',()=>"
                  "console.log(app.address().port));")
        process = subprocess.Popen(["node", "-e", script], cwd=HERE,
            env={**os.environ, "JEV_MODEL_URL": base + "/predict"},
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        try:
            port = process.stdout.readline().strip()
            self.assertTrue(port.isdigit(), "Node connector did not start")
            url = f"http://127.0.0.1:{port}/v1/jev/probability"
            self.assertEqual(pipeline.score_http(url, "Caller: send the code", 2), 0.91)
            self.assertEqual(model.received, ["Caller: send the code"])
            model.fail = True
            with self.assertRaises(urllib.error.HTTPError) as error:
                pipeline.score_http(url, "Caller: hello", 2)
            self.assertEqual(error.exception.code, 503)
            with urllib.request.urlopen(base + "/health") as result:
                self.assertTrue(json.load(result)["modelLoaded"])
            request = urllib.request.Request(base + "/predict", data=b'{"transcript":""}',
                                             headers={"Content-Type": "application/json"})
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(request)
            self.assertEqual(error.exception.code, 400)
        finally:
            process.terminate()
            process.wait(timeout=5)
            process.stdout.close()
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
