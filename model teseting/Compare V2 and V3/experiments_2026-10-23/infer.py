"""CPU inference for V2/V3 on arrays of 4-s windows (same model code as sources/inference.py)."""
from __future__ import annotations
import json, sys, time
from pathlib import Path
import numpy as np, torch, torch.nn as nn
from transformers import Wav2Vec2Config, Wav2Vec2Model

M = Path(__file__).resolve().parent.parent / "inputs/models"
torch.set_num_threads(2)


class AttnStatsPool(nn.Module):
    def __init__(self, d):
        super().__init__(); self.att = nn.Sequential(nn.Linear(d, 128), nn.Tanh(), nn.Linear(128, 1))
    def forward(self, h):
        a = torch.softmax(self.att(h).float(), dim=1).to(h.dtype); mu = (a * h).sum(1)
        sd = torch.sqrt(((a * (h - mu.unsqueeze(1)) ** 2).sum(1)).clamp(min=1e-6)); return torch.cat([mu, sd], -1)


class DeepfakeDetector(nn.Module):
    def __init__(self, keep_layers=12):
        super().__init__()
        cfg = Wav2Vec2Config.from_json_file(str(M / "architecture.json")); cfg.num_hidden_layers = keep_layers; cfg.layerdrop = 0.0
        self.backbone = Wav2Vec2Model(cfg); d = cfg.hidden_size
        self.layer_w = nn.Parameter(torch.zeros(keep_layers + 1))
        self.proj = nn.Sequential(nn.LayerNorm(d), nn.Linear(d, 256), nn.GELU()); self.pool = AttnStatsPool(256)
        self.head = nn.Sequential(nn.Dropout(0.2), nn.Linear(512, 128), nn.GELU(), nn.Dropout(0.2), nn.Linear(128, 1))
    def forward(self, wav, return_feat=False):
        hs = self.backbone(wav, output_hidden_states=True).hidden_states; w = torch.softmax(self.layer_w, 0)
        f = self.pool(self.proj(sum(w[i] * hs[i] for i in range(len(hs)))))
        z = self.head(f).squeeze(-1)
        return (z, f) if return_feat else z


def load(version):
    m = DeepfakeDetector()
    path = M / version / ("best.pt" if version == "v2" else "detector_state.pt")
    st = torch.load(path, map_location="cpu", weights_only=True)
    st = st["model"] if "model" in st else st
    m.load_state_dict(st, strict=True); return m.eval()


def normalize(x):
    x = np.asarray(x, np.float32)
    return ((x - x.mean(-1, keepdims=True)) / (x.std(-1, keepdims=True) + 1e-7)).astype(np.float32)


@torch.no_grad()
def score(model, windows, batch=8, feats=False, log=None):
    Z, F = [], []; t0 = time.time()
    for i in range(0, len(windows), batch):
        z, f = model(torch.from_numpy(np.ascontiguousarray(windows[i:i + batch])), return_feat=True)
        Z.append(z.double().numpy()); F.append(f.float().numpy())
        if log and (i // batch) % 10 == 0:
            print(f"  {log}: {i + len(z)}/{len(windows)} ({time.time() - t0:.0f}s)", flush=True)
    Z = np.concatenate(Z); F = np.concatenate(F)
    return (Z, F) if feats else Z
