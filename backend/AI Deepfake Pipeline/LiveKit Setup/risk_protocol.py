"""Version 1 of the voice assessment wire contract consumed by the iPhone app."""
from __future__ import annotations

import uuid

RISK_TOPIC = "scam-guard.risk"


class RiskPublisher:
    def __init__(self, room: str, caller_identity: str, model: str):
        if model not in ("real", "stub"):
            raise ValueError("model must be real or stub")
        self.room, self.caller_identity, self.model = room, caller_identity, model
        self.stream_id = str(uuid.uuid4())
        self.sequence = 0

    def message(self, payload: dict) -> dict:
        self.sequence += 1
        return {**payload, "schema": 1, "room": self.room,
                "callerIdentity": self.caller_identity, "model": self.model,
                "streamID": self.stream_id, "sequence": self.sequence}
