import copy
import unittest
from probe_checks import ProbeEvidence


def update(sequence, revision=None, **changes):
    result = dict(schema=1, model="real", room="room", callerIdentity="caller", streamID="stream",
                  sequence=sequence, type="risk", infer_ms=900,
                  deepfake={"p_last": .7, "updates": sequence},
                  transcript={"state": "monitoring", "probability": .9, "age_sec": 1,
                              "scored_revision": revision or sequence})
    result.update(changes)
    return result


class ProbeTests(unittest.TestCase):
    def test_requires_sustained_advancing_both_pipelines(self):
        check = ProbeEvidence("room", "caller", 35)
        self.assertFalse(check.observe(update(1), is_agent=True, now=0))
        self.assertFalse(check.observe(update(2), is_agent=True, now=20))
        self.assertTrue(check.observe(update(3), is_agent=True, now=36))

    def test_old_single_transcript_score_never_passes(self):
        check = ProbeEvidence("room", "caller", 35)
        for n in range(1, 60):
            self.assertFalse(check.observe(update(n, revision=1), is_agent=True, now=n))

    def test_spoofs_stubs_wrong_calls_duplicates_and_nonfinite_rejected(self):
        for changes in ({"model": "stub"}, {"room": "other"}, {"callerIdentity": "other"},
                        {"infer_ms": float("nan")}, {"deepfake": {"p_last": True, "updates": 1}},
                        {"deepfake": {"p_last": float("inf"), "updates": 1}}):
            check = ProbeEvidence("room", "caller", 0)
            for n in range(1, 5):
                self.assertFalse(check.observe(update(n, **changes), is_agent=True, now=n))
        check = ProbeEvidence("room", "caller", 0)
        for n in range(1, 5):
            self.assertFalse(check.observe(update(n), is_agent=False, now=n))
        for n in range(4):
            self.assertFalse(check.observe(update(1), is_agent=True, now=n))

    def test_failure_staleness_or_stream_restart_requires_new_healthy_period(self):
        for change in ({"transcript": {"state": "stale"}},
                       {"transcript": {"state": "monitoring", "probability": .9, "age_sec": 20, "scored_revision": 3}},
                       {"streamID": "replacement"}):
            check = ProbeEvidence("room", "caller", 35)
            check.observe(update(1), is_agent=True, now=0)
            check.observe(update(2), is_agent=True, now=20)
            self.assertFalse(check.observe(update(3, **copy.deepcopy(change)), is_agent=True, now=36))
            self.assertFalse(check.observe(update(4), is_agent=True, now=40))


if __name__ == "__main__":
    unittest.main()
