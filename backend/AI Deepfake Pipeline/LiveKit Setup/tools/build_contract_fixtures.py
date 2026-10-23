"""Emit actual session/publisher packets for Python/Swift contract replay."""
import json
from pathlib import Path
import sys
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scoring import AudioScoringSession, ScoringConfig
from risk import sigmoid
from risk_protocol import RiskPublisher


def build():
    detector = type("Detector", (), {"meta": {"window_sec": 4}})()
    pub = RiskPublisher("call-contract", "caller-contract", "real")
    pub.stream_id = "00000000-0000-4000-8000-000000000002"
    session = AudioScoringSession(detector, (.9999904632568359,.9999998807907104),
                                  config=ScoringConfig(current_enabled=True, wire_version="call-evidence-v2"))
    cases = []
    def add(name, now):
        cases.append({"name": name, "payload": pub.message(dict(session.payload(now), t=now))})
    add("v2_actual_no_evidence", 0)
    frame = np.full(64000, 5000, dtype=np.int16).tobytes()
    for now in (4,8,12):
        session.push(frame, now)
        _, generation = session.snapshot(now)
        session.complete({"p_fake": sigmoid(30), "logit": 30, "infer_ms": 20}, generation, now=now+.02)
    add("v2_actual_fresh_warning", 12.02)
    session.push(frame, 16)
    _, generation = session.snapshot(16)
    add("v2_actual_pending", 16.01)
    add("v2_actual_timeout", 26.01)
    session.failed(generation=generation)
    add("v2_actual_failed", 26.02)
    # Recovery after explicit failure is independent of heartbeat receipt.
    session.push(frame, 30)
    _, generation = session.snapshot(30)
    session.complete({"p_fake": sigmoid(-2), "logit": -2, "infer_ms": 20}, generation, now=30.02)
    session.push(frame, 34)
    _, generation = session.snapshot(34)
    session.complete({"p_fake": sigmoid(-2), "logit": -2, "infer_ms": 20}, generation, now=34.02)
    add("v2_actual_recovered", 34.02)
    add("v2_actual_stale", 54)
    return {"kind": "actual_python_session_packets", "cases": cases}


if __name__ == "__main__":
    target = Path(__file__).resolve().parents[1] / "docs/evidence-v2-fixtures.json"
    target.write_text(json.dumps(build(), indent=2, allow_nan=False) + "\n")
    print(target)
