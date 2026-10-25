"""Synthetic stand-ins so the v3 notebook can run end to end offline (CPU, tiny random model).

Not a quality test: it checks that every cell runs, files land where the repo expects, and the
exported bundle loads with the repo's inference.py.
"""
import json, os, sys, subprocess
from pathlib import Path
import numpy as np, pandas as pd, soundfile as sf, torch, torch.nn as nn
from transformers import Wav2Vec2Config, Wav2Vec2Model

root = Path(sys.argv[1]); root.mkdir(parents=True, exist_ok=True)
SR = 16000; rng = np.random.default_rng(0)
drive = root / "drive"; local = root / "local"
(drive / "cache_en").mkdir(parents=True, exist_ok=True)

def voice(sec, f0, fake):
    t = np.arange(int(sec * SR)) / SR
    x = sum(np.sin(2 * np.pi * k * f0 * (1 + .03 * np.sin(2 * np.pi * 3 * t)) * t) / k for k in range(1, 8))
    x *= (np.sin(2 * np.pi * rng.uniform(2, 5) * t) > -.2)              # syllable-like gating
    if fake: x[(t % 1.3) < .15] = 0                                       # TTS-like exact-zero pauses
    else: x += rng.normal(0, .02, len(t))                                 # room noise floor
    return (x / np.abs(x).max() * .9).astype(np.float32)

# v2-style cache: MLAAD-like fakes from 10 systems, M-AILABS-like real from 6 books
rows, chunks, off = [], [], 0
systems = [f"sys{i}" for i in range(10)]
for i in range(220):
    fake = i % 2 == 0
    x = voice(rng.uniform(1.5, 6), rng.uniform(90, 220), fake)
    a = (x * 32767).astype(np.int16); chunks.append(a)
    sysname = systems[i % 10] if fake else "bonafide"
    split = ("test" if sysname in ("sys0", "sys1") else "val" if sysname == "sys2" else "train") if fake else \
            ("test" if i % 12 == 1 else "val" if i % 12 == 3 else "train")
    rows.append(dict(path=f"x/{i}.wav", label=int(fake), system=sysname, group=sysname if fake else f"book{i%6}",
                     offset=off, length=len(a), split=split)); off += len(a)
np.save(drive / "cache_en" / "audio_int16.npy", np.concatenate(chunks))
pd.DataFrame(rows).to_csv(drive / "cache_en" / "manifest.csv", index=False)

# LibriSpeech-like tree (dev-clean only), 8 speakers
for s in range(8):
    d = root / "ls" / "LibriSpeech" / "dev-clean" / str(100 + s) / "1"; d.mkdir(parents=True, exist_ok=True)
    for u in range(6): sf.write(d / f"{100+s}-1-{u:04d}.flac", voice(rng.uniform(2, 5), 100 + 10 * s, False), SR)
# ESC-50-like folder (44.1 kHz)
e = root / "esc" / "ESC-50-master" / "audio"; e.mkdir(parents=True, exist_ok=True)
for k in range(25): sf.write(e / f"1-{k}-A-{k%5}.wav", rng.normal(0, .1, 44100 * 5).astype(np.float32), 44100)
# own data (eval-only), including an mp3 to exercise the ffmpeg decode path
for label, fake in (("real", False), ("fake", True)):
    d = drive / "own_data" / label / f"{label}_src"; d.mkdir(parents=True, exist_ok=True)
    sf.write(d / "a.wav", voice(9, 150, fake), 44100 if False else SR)
    subprocess.run(["ffmpeg", "-loglevel", "quiet", "-y", "-i", str(d / "a.wav"), str(d / "b.mp3")], check=True)

# tiny wav2vec2 architecture + an "init checkpoint" in the v2 best.pt format
arch = Wav2Vec2Config(hidden_size=32, num_hidden_layers=2, num_attention_heads=2, intermediate_size=64,
                      conv_dim=(32,) * 7, feat_extract_norm="layer", do_stable_layer_norm=True,
                      num_conv_pos_embeddings=16, num_conv_pos_embedding_groups=4)
arch.to_json_file(root / "tiny_arch.json")
class AttnStatsPool(nn.Module):
    def __init__(self, d):
        super().__init__(); self.att = nn.Sequential(nn.Linear(d, 128), nn.Tanh(), nn.Linear(128, 1))
class Det(nn.Module):
    def __init__(self):
        super().__init__(); c = Wav2Vec2Config.from_json_file(root / "tiny_arch.json"); c.num_hidden_layers = 2
        self.backbone = Wav2Vec2Model(c); self.layer_w = nn.Parameter(torch.zeros(3))
        self.proj = nn.Sequential(nn.LayerNorm(32), nn.Linear(32, 256), nn.GELU()); self.pool = AttnStatsPool(256)
        self.head = nn.Sequential(nn.Dropout(0.2), nn.Linear(512, 128), nn.GELU(), nn.Dropout(0.2), nn.Linear(128, 1))
torch.manual_seed(0); torch.save({"model": Det().state_dict(), "val_eer": .1}, root / "init_best.pt")

json.dump(dict(DRIVE_DIR=str(drive), LOCAL_DIR=str(local), INIT_CHECKPOINT=str(root / "init_best.pt"),
               EXPECTED_INIT_SHA256=None, KEEP_LAYERS=2, ARCH_CONFIG_JSON=str(root / "tiny_arch.json"),
               LIBRISPEECH_SUBSETS=["dev-clean"], LIBRISPEECH_LOCAL_DIR=str(root / "ls"),
               ESC50_LOCAL_DIR=str(root / "esc"), SMOKE_TEST=True, LS_VAL_FRAC=.25, LS_TEST_FRAC=.25),
          open(root / "overrides.json", "w"), indent=1)
print("fixture ready in", root)
