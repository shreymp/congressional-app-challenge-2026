"""Few-shot head correction on frozen V3 features, strictly leave-one-recording-out.

Score = logistic regression on [V3 logit, top-k PCA of V3's 512-d pooled features], fit on
the other 4 recordings (all conditions). The held-out recording is never seen.
"""
import json, numpy as np, collections
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from common import *

rows = load_rows()
d = np.load("cache/v3_orig.npz"); F = d["f"]
res = []
for k in (0, 2, 4, 8, 16):
    for C in (0.01, 0.1, 1.0):
        oof, preds, states = {}, {}, {}
        for held in SOURCES:
            tr = [r for r in rows if r["src"] != held]; te = [r for r in rows if r["src"] == held]
            def X(rs, fit=False):
                z = np.array([[r["v3"]] for r in rs])
                if k == 0: return z
                f = F[[r["idx"] for r in rs]]
                return np.hstack([z, pca.transform(sc.transform(f))])
            if k:
                sc = StandardScaler().fit(F[[r["idx"] for r in tr]]); pca = PCA(k, random_state=0).fit(sc.transform(F[[r["idx"] for r in tr]]))
            ytr = np.array([r["y"] for r in tr])
            m = LogisticRegression(C=C, class_weight="balanced", max_iter=2000).fit(X(tr), ytr)
            str_ = m.decision_function(X(tr)); ste = m.decision_function(X(te))
            hu = np.sort(str_[ytr == 0])[::-1]; thr = hu[int(0.02 * len(hu))] + 1e-9
            a, b = platt(str_, ytr)
            for r, s in zip(te, ste):
                r["h"] = float(s); preds[(r["case"], r["start"])] = (r["y"], s >= thr, r["condition"])
            states.update(call_states(te, "h", calib=(a, b)))
        y = np.array([v[0] for v in preds.values()]); p = np.array([v[1] for v in preds.values()])
        nz = np.array([v[2].startswith("white_noise") for v in preds.values()])
        def rr(mask):
            ai = p[mask & (y == 1)].mean(); fp = p[mask & (y == 0)].mean(); return dict(ai=round(float(ai), 3), fp=round(float(fp), 3), bal=round(float((ai + 1 - fp) / 2), 3))
        res.append(dict(k=k, C=C, all=rr(np.ones_like(y, bool)), no_noise=rr(~nz), noise=rr(nz), calls=summarize_calls(states)))
        print(res[-1], flush=True)
json.dump(res, open("results_head.json", "w"), indent=1)
