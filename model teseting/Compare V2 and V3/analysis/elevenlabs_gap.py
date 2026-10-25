"""Follow-up analysis for ELEVENLABS_PLAN.md. Reads saved logits only; runs no model.

Run from the project root:
  .venv/bin/python 'model teseting/Compare V2 and V3/analysis/elevenlabs_gap.py'

Prints (1) AI detection at matched human false-positive rates, (2) where V3's
missed ElevenLabs windows are, and (3) a call-level replay of each case through the
app's CallEvidenceEngine (call-evidence-v1, the default when CURRENT_EVIDENCE is off).
Everything here is measured on the same 5 development recordings as the comparison:
it diagnoses the gap, it is NOT a basis for choosing deployment thresholds.
"""
import collections, csv, json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "backend/AI Deepfake Pipeline/LiveKit Setup"))
from risk import CallEvidenceEngine, sigmoid  # noqa: E402

THR = {"v2": (11.560348981416222, 15.942385033669446), "v3": (2.03125, 6.000000000000001)}
rows = list(csv.DictReader(open(HERE.parent / "results/per_window.csv")))
speech = [r for r in rows if r["scope"] == "speech" and r["label"] in ("ai", "human")]
noise = lambda c: c.startswith("white_noise")
out = {}

def logits(m, label, keep=lambda c: True):
    return [float(r[f"{m}_logit"]) for r in speech if r["label"] == label and keep(r["condition"])]

def rate(xs, t):
    return sum(x >= t for x in xs) / len(xs)

# 1. Matched false-positive comparison: threshold placed just above the k-th highest human window
out["matched_fp"] = []
for m in ("v2", "v3"):
    ai, hu = logits(m, "ai"), sorted(logits(m, "human"), reverse=True)
    for k in (0, 4, 10, 20, 31, 112):
        t = hu[k] + 1e-9
        out["matched_fp"].append(dict(model=m, human_fp=rate(hu, t), ai_detected=rate(ai, t)))

# 2. Where V3 misses at its supplied EER threshold
out["v3_split"] = {}
for name, keep in (("no_white_noise", lambda c: not noise(c)), ("white_noise_only", noise)):
    for m in ("v2", "v3"):
        out["v3_split"][f"{m}/{name}"] = dict(ai_detected=rate(logits(m, "ai", keep), THR[m][0]),
                                              human_fp=rate(logits(m, "human", keep), THR[m][0]))
miss = collections.Counter(("white_noise" if noise(r["condition"]) else "other", r["source_groups"].replace("ai_source", "shrey").split("_ivc")[0].split("_")[-1])
                           for r in speech if r["label"] == "ai" and float(r["v3_logit"]) < THR["v3"][0])
out["v3_missed_windows"] = {f"{a} | {b}": n for (a, b), n in sorted(miss.items())}

# 3. Call-level replay (windows in time order, weight 1)
cases = collections.defaultdict(list)
for r in speech:
    cases[(r["condition"], r["source_groups"], r["label"])].append(r)

def replay(m, elevated, high):
    c = collections.Counter()
    for (cond, src, label), ws in cases.items():
        e, ever = CallEvidenceEngine(sigmoid(elevated), sigmoid(high)), False
        for r in sorted(ws, key=lambda r: float(r["start_sec"])):
            z = float(r[f"{m}_logit"]); s = e.update(sigmoid(z), z=z); ever |= s["recent_ai"]
        c[f"{label}->{s['state']}"] += 1
        c[f"{label}->warning_shown_at_some_point"] += ever
    return dict(sorted(c.items()))

out["call_level"] = {"v2 supplied thresholds": replay("v2", *THR["v2"]),
                     "v3 supplied thresholds": replay("v3", *THR["v3"]),
                     "v3 DIAGNOSTIC ONLY high=elevated=2.03": replay("v3", THR["v3"][0], THR["v3"][0])}
print(json.dumps(out, indent=1))
