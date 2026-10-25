"""Offline tests for the production audio path and the shared Swift wire fixtures.
Run: python -m unittest discover -s "backend/AI Deepfake Pipeline/LiveKit Setup" -p test_integration.py -v
Regenerate fixtures intentionally: python test_integration.py --write-fixtures
"""
import json
import math
from pathlib import Path
import sys
import unittest

import numpy as np
from risk import CallEvidenceEngine, RiskEngine, sigmoid
from risk_protocol import RiskPublisher
from scoring import AudioScoringSession

FIXTURE = Path(__file__).resolve().parents[3] / "ios/CallmaTests/Fixtures/deepfake-wire.json"
THRESHOLDS = (0.9999904632568359, 0.9999998807907104)


class FakeDetector:
    meta = {"window_sec": 4.0}


def evidence(z, steps):
    risk = RiskEngine(*THRESHOLDS)
    for _ in range(steps):
        result = risk.update(sigmoid(z), z)
    return result


def wire_fixtures():
    pub = RiskPublisher("call-test", "sip-test", "real")
    pub.stream_id = "00000000-0000-4000-8000-000000000001"
    cases = []
    for name, expected, payload in [
        ("waiting", "waiting", {"type": "status", "state": "waiting"}),
        ("first_score", "analyzing", {"type": "risk", "deepfake": evidence(-2, 1)}),
        ("human", "human", {"type": "risk", "deepfake": evidence(-2, 3)}),
        ("elevated", "uncertain", {"type": "risk", "deepfake": evidence(13, 3)}),
        ("high", "ai", {"type": "risk", "deepfake": evidence(20, 3)}),
        # The overall transcript level must never be used as the voice verdict.
        ("transcript_only", "human", {"type": "risk", "level": "prevention", "deepfake": evidence(-2, 3)}),
        ("failed", "unavailable", {"type": "status", "state": "unavailable"}),
    ]:
        cases.append({"name": name, "expected": expected, "payload": pub.message(payload)})
    stub = pub.message({"type": "risk", "deepfake": evidence(20, 3)})
    stub["model"] = "stub"
    cases.append({"name": "stub_never_a_verdict", "expected": "unavailable", "payload": stub})
    for name, z, expected in [("cumulative_human", -2, "human"), ("cumulative_ai", 20, "ai"),
                               ("cumulative_mixed", 13.75, "uncertain")]:
        engine = CallEvidenceEngine(*THRESHOLDS)
        for _ in range(3):
            result = engine.update(sigmoid(z), z)
        cases.append({"name": name, "expected": expected,
                      "payload": pub.message({"type": "risk", "deepfake": result})})
    return {"cases": cases}


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.session = AudioScoringSession(FakeDetector(), THRESHOLDS)
        t = np.arange(320) / 16000
        self.frame = (np.sin(2 * np.pi * 220 * t) * 5000).astype(np.int16).tobytes()

    def feed(self, start, seconds, speech=True):
        for n in range(round(seconds * 50)):
            self.session.push(self.frame if speech else bytes(640), start + (n + 1) / 50)

    def score(self, now, z):
        audio, generation = self.session.snapshot(now)
        self.assertGreaterEqual(len(audio), 48000)
        self.session.complete({"p_fake": sigmoid(z), "logit": z, "infer_ms": 20}, generation)
        return self.session.payload(now)

    def test_silence_never_reaches_model_and_requires_complete_contiguous_window(self):
        self.feed(0, 8, speech=False)
        self.assertIsNone(self.session.snapshot(8))
        self.feed(8, 1.48)
        self.assertIsNone(self.session.snapshot(9.48))
        self.feed(9.48, .02)
        self.assertIsNotNone(self.session.snapshot(9.5))

    def test_human_requires_multiple_distinct_windows_and_no_rescoring_silence(self):
        self.feed(0, 4)
        first = self.score(4, -2)
        self.assertEqual(first["deepfake"]["human_steps"], 1)
        self.assertIsNone(self.session.snapshot(4.01))
        self.feed(4, 1)
        self.assertIsNone(self.session.snapshot(5))
        self.feed(5, 3)
        last = self.score(8, -2)
        self.assertEqual(last["deepfake"]["state"], "human")
        self.feed(8, 4)
        last = self.score(12, -2)
        self.assertEqual(last["deepfake"]["human_steps"], 3)
        self.feed(12, 4, speech=False)
        self.assertIsNone(self.session.snapshot(16))

    def test_pause_preserves_accumulated_evidence_and_valid_inflight_result(self):
        self.feed(0, 4)
        _, generation = self.session.snapshot(4)
        self.session.refresh(11)
        self.session.complete({"p_fake": 1, "logit": 30, "infer_ms": 1}, generation)
        self.assertEqual(self.session.payload(11)["deepfake"]["updates"], 1)
        self.feed(11, 2)
        self.assertIsNone(self.session.snapshot(13))
        self.assertEqual(self.session.risk.n_updates, 1)
        self.feed(13, 2)
        self.assertEqual(self.score(15, 30)["deepfake"]["state"], "ai")

    def test_slow_inference_becomes_unavailable_without_queuing_more_work(self):
        self.feed(0, 4)
        self.session.snapshot(4)
        self.feed(4, 11)
        self.assertIsNone(self.session.snapshot(15))
        self.assertEqual(self.session.payload(15)["state"], "unavailable")
        self.session.failed()
        self.assertIsNotNone(self.session.snapshot(15))

    def test_nonfinite_scores_fail_and_later_inference_recovers(self):
        self.feed(0, 4)
        _, generation = self.session.snapshot(4)
        with self.assertRaises(ValueError):
            self.session.complete({"p_fake": math.nan, "logit": 0, "infer_ms": 1}, generation)
        self.session.failed()
        self.assertEqual(self.session.payload(4)["state"], "unavailable")
        self.feed(4, 4)
        self.assertEqual(self.score(8, -2)["type"], "risk")

    def test_risk_escalates_and_deescalates_with_hysteresis(self):
        engine = RiskEngine(*THRESHOLDS, alpha=1)
        self.assertEqual(engine.update(1, 20)["level"], "listening")
        engine.update(1, 20)
        self.assertEqual(engine.update(1, 20)["level"], "high")
        for _ in range(4):
            self.assertEqual(engine.update(0, -2)["level"], "high")
        low = engine.update(0, -2)
        self.assertEqual(low["level"], "listening")
        self.assertGreaterEqual(low["human_steps"], 3)

    def test_invalid_thresholds_or_scores_do_not_produce_labels(self):
        for thresholds in [(0, 1), (.9, .8), (math.nan, .99)]:
            with self.assertRaises(ValueError):
                RiskEngine(*thresholds)
        for p, z in [(math.nan, 0), (2, 0), (.5, math.inf)]:
            with self.assertRaises(ValueError):
                RiskEngine(*THRESHOLDS).update(p, z)

    def test_protocol_sequence_stream_and_caller_scope(self):
        publisher = RiskPublisher("call-A", "caller-A", "real")
        first = publisher.message({"type": "status", "state": "waiting", "room": "forged"})
        second = publisher.message({"type": "status", "state": "unavailable"})
        self.assertEqual(first["room"], "call-A")
        self.assertEqual(first["callerIdentity"], "caller-A")
        self.assertEqual(first["schema"], 1)
        self.assertEqual(second["sequence"], first["sequence"] + 1)
        self.assertEqual(second["streamID"], first["streamID"])
        self.assertNotEqual(RiskPublisher("call-A", "caller-A", "real").stream_id, publisher.stream_id)
        json.dumps(first, allow_nan=False)

    def test_swift_fixtures_match_production_risk_engine(self):
        actual = {case["name"]: case for case in json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]}
        for case in wire_fixtures()["cases"]:
            self.assertEqual(actual[case["name"]], case)


if __name__ == "__main__":
    if "--write-fixtures" in sys.argv:
        FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        FIXTURE.write_text(json.dumps(wire_fixtures(), indent=2) + "\n", encoding="utf-8")
        print(FIXTURE)
    else:
        unittest.main()
