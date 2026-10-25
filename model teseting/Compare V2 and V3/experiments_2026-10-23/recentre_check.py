"""Replay every case through the app's CallEvidenceEngine with V3's current thresholds vs the
recommended re-centred pair. Reads saved logits only (results/per_window.csv); no model run.

  cd 'model teseting/Compare V2 and V3/experiments_2026-10-23' && python3 recentre_check.py
"""
import collections, csv
from common import CMP, V3_EER, V3_HIGH, load_rows, call_states, summarize_calls
from risk import CallEvidenceEngine, sigmoid, logit

RECENTRED = (0.046875, 4.015625)   # THRESHOLD_ELEVATED_LOGIT, THRESHOLD_HIGH_LOGIT
c, s = (RECENTRED[0] + RECENTRED[1]) / 2, (RECENTRED[1] - RECENTRED[0]) / (2 * logit(.65))
print(f"re-centred engine: center {c:.5f} (= V3 logit_threshold_eer {V3_EER}), scale {s:.4f} (unchanged)")

rows = load_rows()
for name, thr in (("current V3 config", (V3_EER, V3_HIGH)), ("re-centred", RECENTRED)):
    print(f"\n{name}: speech cases {summarize_calls(call_states(rows, 'v3', thresholds=thr))}")

allw = list(csv.DictReader(open(CMP / "results/per_window.csv")))
cases = collections.defaultdict(list)
for r in allw:
    if r["scope"] != "speech": cases[r["case"]].append(r)
for name, (el, hi) in (("current V3 config", (V3_EER, V3_HIGH)), ("re-centred", RECENTRED)):
    print(f"\n{name}: non-speech probes and constructed transitions")
    for case, ws in sorted(cases.items()):
        e = CallEvidenceEngine(sigmoid(el), sigmoid(hi)); warn = None
        for r in sorted(ws, key=lambda r: float(r["start_sec"])):
            z = float(r["v3_logit"]); st = e.update(sigmoid(z), z=z)
            if st["recent_ai"] and warn is None: warn = float(r["end_sec"])
        print(f"  {case[:60]:60s} final={st['state']:9s} first_warning_at={warn}")
