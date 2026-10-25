"""Score every speech signal at a 2-s hop (base 4-s grid + half-offset windows), V3 and V2."""
import hashlib, json, numpy as np, time
from infer import load, score, normalize
from common import CMP, source_of
S = np.load("cache/signals.npz")
man = json.load(open(CMP/"inputs/window_manifest.json"))
keys = sorted({f"{source_of(w['source_groups'])}|{w['condition']}" for w in man if w["scope"]=="speech" and w["label"] in ("ai","human")})
index, arrays, grid = {}, [], []   # grid: (key, start_sec, array_idx)
for k in keys:
    s = S[k]
    for st in range(0, len(s) - 64000 + 1, 32000):
        a = normalize(s[st:st+64000]); h = hashlib.sha256(a.tobytes()).hexdigest()
        if h not in index: index[h] = len(arrays); arrays.append(a)
        grid.append((k, st/16000, index[h]))
X = np.stack(arrays); print("unique windows", len(X), flush=True)
json.dump(grid, open("cache/shift_grid.json","w"))
for v in ("v3","v2"):
    t=time.time(); z = score(load(v), X, log="shift-"+v); np.save(f"cache/shift_{v}.npy", z); print("DONE shift", v, f"{time.time()-t:.0f}s", flush=True)
