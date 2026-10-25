"""Shared evaluation for the ElevenLabs-improvement experiments.

Every fitted parameter is chosen leave-one-recording-out (LORO): fit on 4 of the 5
source recordings (all their conditions), score the 5th. Threshold-free numbers (AUC,
EER, detection at matched false-flag rates) are reported on all windows.
"""
from __future__ import annotations
import csv, math, sys, collections
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
U = HERE.parents[2]  # repo root
CMP = HERE.parent  # "Compare V2 and V3"
sys.path.insert(0, str(U / "backend/AI Deepfake Pipeline/LiveKit Setup"))
from risk import CallEvidenceEngine, sigmoid  # noqa: E402

V3_EER, V3_HIGH = 2.03125, 6.000000000000001
V2_EER, V2_HIGH = 11.560348981416222, 15.942385033669446
SOURCES = ("shrey", "keshav", "azim", "h1320", "h6930")


def source_of(groups: str) -> str:
    g = groups
    if g == "ai_source": return "shrey"
    if "keshav" in g: return "keshav"
    if "azim" in g: return "azim"
    if "1320" in g: return "h1320"
    if "6930" in g: return "h6930"
    raise ValueError(g)


def load_rows():
    rows = list(csv.DictReader(open(CMP / "results/per_window.csv")))
    out = []
    for r in rows:
        if r["scope"] != "speech" or r["label"] not in ("ai", "human"):
            continue
        out.append(dict(case=r["case"], condition=r["condition"], src=source_of(r["source_groups"]),
                        y=1 if r["label"] == "ai" else 0, start=float(r["start_sec"]),
                        idx=int(r["array_index"]), v2=float(r["v2_logit"]), v3=float(r["v3_logit"])))
    return out


def auc(y, s):
    y, s = np.asarray(y), np.asarray(s, float)
    pos, neg = s[y == 1], s[y == 0]
    gt = (pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()
    return gt / (len(pos) * len(neg))


def eer(y, s):
    y, s = np.asarray(y), np.asarray(s, float)
    best = (2, 0)
    for t in np.unique(s):
        fpr = (s[y == 0] >= t).mean(); fnr = (s[y == 1] < t).mean()
        if abs(fpr - fnr) < best[0]: best = (abs(fpr - fnr), (fpr + fnr) / 2)
    return best[1]


def det_at_fp(y, s, fp_target):
    """AI detection with threshold just above the human score that gives <= fp_target flagged."""
    y, s = np.asarray(y), np.asarray(s, float)
    hu = np.sort(s[y == 0])[::-1]
    k = int(math.floor(fp_target * len(hu)))
    t = hu[k] + 1e-9 if k < len(hu) else -np.inf
    return float((s[y == 1] >= t).mean()), float((hu >= t).mean())


def rates(y, s, t):
    y, s = np.asarray(y), np.asarray(s, float)
    ai = float((s[y == 1] >= t).mean()); fp = float((s[y == 0] >= t).mean())
    return dict(ai_detected=ai, human_fp=fp, balanced=(ai + 1 - fp) / 2)


def platt(z, y):
    """Class-balanced 1-D logistic fit: P(ai) = sigmoid(a*z + b). Returns (a, b)."""
    from sklearn.linear_model import LogisticRegression
    m = LogisticRegression(C=1e4, class_weight="balanced").fit(np.asarray(z, float)[:, None], y)
    return float(m.coef_[0, 0]), float(m.intercept_[0])


def call_states(rows, score_key, calib=None, thresholds=None):
    """Replay each (case) through the app's CallEvidenceEngine. Returns {case: (y, src, cond, final_state, warned)}."""
    cases = collections.defaultdict(list)
    for r in rows: cases[r["case"]].append(r)
    out = {}
    for case, ws in cases.items():
        ws = sorted(ws, key=lambda r: r["start"])
        el, hi = thresholds or (V3_EER, V3_HIGH)
        cal = None if calib is None else dict(a=calib[0], b=calib[1])
        e = CallEvidenceEngine(sigmoid(el), sigmoid(hi), calibration=cal)
        warned = False
        for r in ws:
            z = float(r[score_key]); s = e.update(sigmoid(z), z=z); warned |= s["recent_ai"]
        out[case] = (ws[0]["y"], ws[0]["src"], ws[0]["condition"], s["state"], warned)
    return out


def summarize_calls(states):
    c = collections.Counter()
    for y, src, cond, st, warned in states.values():
        lab = "ai" if y else "human"
        c[f"{lab}->{st}"] += 1
        if warned: c[f"{lab}_warned"] += 1
    return dict(sorted(c.items()))


def loro(rows, score_key, fit_fn):
    """fit_fn(train_rows) -> (threshold, calib). Returns window predictions & call states from held-out folds."""
    preds, states = {}, {}
    for held in SOURCES:
        train = [r for r in rows if r["src"] != held]
        test = [r for r in rows if r["src"] == held]
        thr, calib = fit_fn(train)
        for r in test:
            preds[(r["case"], r["start"])] = (r["y"], r[score_key] >= thr, r["condition"])
        states.update(call_states(test, score_key, calib=calib))
    y = np.array([v[0] for v in preds.values()]); p = np.array([v[1] for v in preds.values()])
    noise = np.array([v[2].startswith("white_noise") for v in preds.values()])
    def r(mask):
        ai = p[mask & (y == 1)].mean(); fp = p[mask & (y == 0)].mean()
        return dict(ai_detected=round(float(ai), 4), human_fp=round(float(fp), 4), balanced=round(float((ai + 1 - fp) / 2), 4))
    return dict(window_all=r(np.ones_like(y, bool)), window_no_noise=r(~noise), window_noise=r(noise),
                calls=summarize_calls(states))


def fit_threshold_fp(train, key, fp_target=0.02):
    z = np.array([r[key] for r in train]); y = np.array([r["y"] for r in train])
    hu = np.sort(z[y == 0])[::-1]; k = int(math.floor(fp_target * len(hu)))
    return hu[k] + 1e-9


def standard_fit(key, fp_target=0.02):
    def f(train):
        z = np.array([r[key] for r in train]); y = np.array([r["y"] for r in train])
        return fit_threshold_fp(train, key, fp_target), platt(z, y)
    return f


def report(rows, key, name, fp_target=0.02):
    y = np.array([r["y"] for r in rows]); s = np.array([r[key] for r in rows])
    out = dict(method=name, auc=round(float(auc(y, s)), 4), eer=round(float(eer(y, s)), 4))
    for fp in (0.02, 0.05, 0.10):
        out[f"det_at_{int(fp*100)}pct_fp"] = round(det_at_fp(y, s, fp)[0], 4)
    out["loro"] = loro(rows, key, standard_fit(key, fp_target))
    return out
