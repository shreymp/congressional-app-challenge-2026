"""Rebuild every speech case's full PCM signal exactly as compare.py did; verify window hashes."""
import hashlib, json, math, numpy as np, soundfile as sf, importlib.util
from scipy.signal import resample_poly
from common import CMP, source_of
spec = importlib.util.spec_from_file_location("legacy", CMP/"sources/evaluate.py"); legacy = importlib.util.module_from_spec(spec)
src = open(CMP/"sources/evaluate.py").read()
# exec only the helper definitions we need (module has Mac-specific paths in main())
ns = {"np": np, "sf": sf, "resample_poly": resample_poly, "SR": 16000, "__file__": str(CMP/"sources/evaluate.py"), "__name__": "legacy"}
exec(compile("\n".join(l for l in src.split("\n")), "evaluate.py", "exec"), ns)
ns["np"], ns["sf"], ns["resample_poly"], ns["SR"] = np, sf, resample_poly, 16000
def decode(path):
    x, rate = sf.read(path, dtype="float32", always_2d=True); x = x.mean(1)
    if rate != 16000:
        g = math.gcd(rate, 16000); x = resample_poly(x, 16000 // g, rate // g).astype(np.float32)
    return x
aud = CMP/"inputs/audio"
signals = {}
for p in sorted(aud.glob("ElevenLabs*.mp3")):
    x = decode(p); name = "shrey" if "shrey" in p.name else "keshav" if "keshav" in p.name else "azim"
    for cond, s in ns["conditions"](x).items(): signals[(name, cond)] = ns["pcm"](s).astype(np.float32) / 32768
for p in sorted(aud.glob("*40s.wav")):
    h = decode(p)[:40*16000]; name = "h1320" if "1320" in p.name else "h6930"
    for cond, s in ns["conditions"](h).items(): signals[(name, cond)] = ns["pcm"](s).astype(np.float32) / 32768
man = json.load(open(CMP/"inputs/window_manifest.json"))
ok = bad = 0
for w in man:
    if w["scope"] != "speech" or w["label"] not in ("ai", "human"): continue
    key = (source_of(w["source_groups"]), w["condition"]); a = signals[key][int(w["start_sec"]*16000):int(w["start_sec"]*16000)+64000]
    norm = ((a - a.mean()) / (a.std() + 1e-7)).astype(np.float32)
    ok += hashlib.sha256(norm.tobytes()).hexdigest() == w["input_sha256"]; bad += hashlib.sha256(norm.tobytes()).hexdigest() != w["input_sha256"]
print("hash match", ok, "mismatch", bad)
np.savez_compressed("cache/signals.npz", **{f"{k[0]}|{k[1]}": v for k, v in signals.items()})
