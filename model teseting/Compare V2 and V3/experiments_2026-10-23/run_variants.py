import sys, numpy as np, time
from scipy.signal import resample_poly
from infer import load, score, normalize
from common import CMP
import noisereduce as nr
W = np.asarray(np.load(CMP/"inputs/windows.npy"))
def band(x): return np.stack([resample_poly(resample_poly(w,1,2),2,1)[:len(w)] for w in x]).astype(np.float32)
def denoise(x): return np.stack([nr.reduce_noise(y=w, sr=16000, stationary=True, prop_decrease=0.9) for w in x]).astype(np.float32)
jobs = sys.argv[1:]
models = {}
for job in jobs:
    v, var = job.split(":")
    out = f"cache/{v}_{var}.npz"
    import os
    if os.path.exists(out): print("skip", out); continue
    if v not in models: models = {v: load(v)}
    X = W if var == "orig" else normalize(band(W)) if var == "band" else normalize(denoise(W)) if var == "denoise" else None
    t = time.time(); z, f = score(models[v], X, feats=True, log=job)
    np.savez(out, z=z, f=f); print("DONE", job, f"{time.time()-t:.0f}s", flush=True)
