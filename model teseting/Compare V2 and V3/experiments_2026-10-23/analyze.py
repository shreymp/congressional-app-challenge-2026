import csv, json, os, sys, numpy as np, collections
from common import *

rows = load_rows()
allw = list(csv.DictReader(open(CMP / "results/per_window.csv")))
nonspeech = [(int(r["array_index"]), float(r["v2_logit"]), float(r["v3_logit"])) for r in allw if r["scope"] == "non_speech_control"]

Z = {}
for f in sorted(os.listdir("cache")):
    if f.endswith(".npz") and f != "signals.npz":
        d = np.load("cache/" + f); Z[f[:-4]] = d["z"]

def add(name, fn):
    for r in rows: r[name] = fn(r)
    return name

methods = []
methods.append(("V3 as is (baseline)", add("m_v3", lambda r: r["v3"]), True, lambda i: Z["v3_orig"][i] if "v3_orig" in Z else None))
if "v3_band" in Z:
    methods.append(("V3 on 8 kHz band-limited input", add("m_band", lambda r: Z["v3_band"][r["idx"]]), True, lambda i: Z["v3_band"][i]))
    methods.append(("V3 avg(original, 8 kHz)", add("m_avgband", lambda r: (r["v3"] + Z["v3_band"][r["idx"]]) / 2), True, lambda i: (Z["v3_orig"][i] + Z["v3_band"][i]) / 2))
if "v3_denoise" in Z:
    methods.append(("V3 on denoised input", add("m_dn", lambda r: Z["v3_denoise"][r["idx"]]), True, lambda i: Z["v3_denoise"][i]))
    methods.append(("V3 avg(original, denoised)", add("m_avgdn", lambda r: (r["v3"] + Z["v3_denoise"][r["idx"]]) / 2), True, lambda i: (Z["v3_orig"][i] + Z["v3_denoise"][i]) / 2))
    methods.append(("V3 max(original, denoised)", add("m_maxdn", lambda r: max(r["v3"], Z["v3_denoise"][r["idx"]])), True, lambda i: max(Z["v3_orig"][i], Z["v3_denoise"][i])))
if "v3_band" in Z and "v3_denoise" in Z:
    methods.append(("V3 avg(original, 8 kHz, denoised)", add("m_avg3", lambda r: (r["v3"] + Z["v3_band"][r["idx"]] + Z["v3_denoise"][r["idx"]]) / 3), True,
                    lambda i: (Z["v3_orig"][i] + Z["v3_band"][i] + Z["v3_denoise"][i]) / 3))
for w in (0.3, 0.5, 1.0):
    methods.append((f"V3 + {w}*V2 fusion", add(f"m_f{w}", lambda r, w=w: r["v3"] + w * r["v2"]), False, None))

out = []
for name, key, same_scale, ns_fn in methods:
    y = np.array([r["y"] for r in rows]); s = np.array([r[key] for r in rows])
    rep = report(rows, key, name)
    if same_scale: rep["at_v3_supplied_threshold"] = {k: round(v, 4) for k, v in rates(y, s, V3_EER).items()}
    # non-speech: threshold fit on all speech windows at ~2% human FP (same rule for every method)
    t = fit_threshold_fp(rows, key, 0.02)
    if ns_fn is not None:
        ns = np.array([ns_fn(i) for i, _, _ in nonspeech])
    else:
        w = float(name.split("+ ")[1].split("*")[0]); ns = np.array([v3 + w * v2 for _, v2, v3 in nonspeech])
    rep["nonspeech_flagged_at_2pct_threshold"] = f"{int((ns >= t).sum())}/{len(ns)}"
    if same_scale: rep["nonspeech_flagged_at_v3_threshold"] = f"{int((ns >= V3_EER).sum())}/{len(ns)}"
    out.append(rep)
json.dump(out, open("results_variants.json", "w"), indent=1)
for r in out:
    l = r["loro"]
    print(f"\n## {r['method']}\n  AUC {r['auc']}  EER {r['eer']}  det@2/5/10% FP {r['det_at_2pct_fp']}/{r['det_at_5pct_fp']}/{r['det_at_10pct_fp']}")
    if "at_v3_supplied_threshold" in r: print("  at V3 threshold 2.03:", r["at_v3_supplied_threshold"], "| nonspeech", r["nonspeech_flagged_at_v3_threshold"])
    print("  nonspeech @2%-FP threshold:", r["nonspeech_flagged_at_2pct_threshold"])
    print("  LORO all", l["window_all"], "\n       no-noise", l["window_no_noise"], "\n       noise", l["window_noise"], "\n       calls", l["calls"])
