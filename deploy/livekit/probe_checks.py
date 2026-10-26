"""Validate sustained, fresh evidence from one authenticated cloud-agent stream."""
import math


def finite(value, low=0, high=1):
    return type(value) in (int, float) and math.isfinite(value) and low <= value <= high


class ProbeEvidence:
    def __init__(self, room, caller, min_seconds=35, expected_jev=None):
        self.room, self.caller, self.min_seconds = room, caller, min_seconds
        self.expected_jev = expected_jev
        self.stream = None
        self.sequence = 0
        self.since = None
        self.revisions = set()
        self.windows = set()
        self.summary = {}

    def observe(self, message, *, is_agent, now):
        if not is_agent or not isinstance(message, dict):
            return False
        if (message.get("schema") != 1 or message.get("model") != "real"
                or message.get("callerIdentity") != self.caller or message.get("room") != self.room):
            return False
        stream, sequence = message.get("streamID"), message.get("sequence")
        if not isinstance(stream, str) or not stream or type(sequence) is not int or sequence <= 0:
            return False
        if stream != self.stream:
            self.stream, self.sequence, self.since = stream, 0, None
            self.revisions.clear()
            self.windows.clear()
        if sequence <= self.sequence:
            return False
        self.sequence = sequence
        text, voice = message.get("transcript"), message.get("deepfake")
        if not isinstance(text, dict) or not isinstance(voice, dict):
            self.since = None
            self.revisions.clear()
            self.windows.clear()
            return False
        revision, windows = text.get("scored_revision"), voice.get("updates")
        diag = message.get("diag") or {}
        matching_jev = (self.expected_jev is None or
                        (diag.get("jevVersion"), diag.get("jevSha256")) == self.expected_jev)
        valid = (matching_jev and message.get("type") == "risk" and finite(voice.get("p_last"))
                 and finite(message.get("infer_ms"), 0, 10000)
                 and text.get("state") == "monitoring" and finite(text.get("probability"))
                 and finite(text.get("age_sec"), 0, 15)
                 and type(revision) is int and revision > 0
                 and type(windows) is int and windows > 0)
        if not valid:
            self.since = None
            self.revisions.clear()
            self.windows.clear()
            return False
        if self.since is None:
            self.since = now
        self.revisions.add(revision)
        self.windows.add(windows)
        self.summary = dict(model="real", schema=1, deepfake=True, transcript=True,
                            transcript_revision=revision, distinct_revisions=len(self.revisions),
                            distinct_windows=len(self.windows), sustained_sec=round(now-self.since, 1),
                            infer_ms=message["infer_ms"])
        if self.expected_jev:
            self.summary.update(jev_version=diag["jevVersion"], jev_sha256=diag["jevSha256"])
        return (now-self.since >= self.min_seconds and len(self.revisions) >= 3
                and len(self.windows) >= 3)
