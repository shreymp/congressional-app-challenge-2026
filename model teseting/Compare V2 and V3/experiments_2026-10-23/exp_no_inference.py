import json, numpy as np
from common import *
rows = load_rows()
res = []
# Baselines with supplied thresholds (no fitting)
for key, el, hi in (("v2", V2_EER, V2_HIGH), ("v3", V3_EER, V3_HIGH)):
    y = np.array([r["y"] for r in rows]); s = np.array([r[key] for r in rows])
    res.append(dict(method=f"{key} supplied thresholds", **rates(y, s, el),
                    calls=summarize_calls(call_states(rows, key, thresholds=(el, hi)))))
res.append(report(rows, "v3", "v3 + LORO threshold@2%FP + LORO Platt call calibration"))
# Fusion z3 + w*z2, w chosen LORO by training AUC
for r in rows: r["v2c"] = r["v2"]
ws = [0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0]
for w in ws:
    for r in rows: r[f"f{w}"] = r["v3"] + w * r["v2"]
    res.append(report(rows, f"f{w}", f"fusion v3+{w}*v2 (fixed w)"))
print(json.dumps(res, indent=1))
