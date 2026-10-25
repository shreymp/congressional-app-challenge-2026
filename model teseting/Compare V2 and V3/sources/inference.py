# Standalone inference for the CAC deepfake detector.  pip install torch transformers numpy scipy
import json, os, numpy as np, torch, torch.nn as nn
from scipy.signal import resample_poly
from transformers import Wav2Vec2Config, Wav2Vec2Model

class AttnStatsPool(nn.Module):
    def __init__(self, d):
        super().__init__(); self.att = nn.Sequential(nn.Linear(d, 128), nn.Tanh(), nn.Linear(128, 1))
    def forward(self, h):
        a = torch.softmax(self.att(h).float(), dim=1).to(h.dtype); mu = (a * h).sum(1)
        sd = torch.sqrt(((a * (h - mu.unsqueeze(1)) ** 2).sum(1)).clamp(min=1e-6)); return torch.cat([mu, sd], -1)

class DeepfakeDetector(nn.Module):
    def __init__(self, base, keep_layers):
        super().__init__()
        cfg = Wav2Vec2Config.from_pretrained(base); cfg.num_hidden_layers = keep_layers; cfg.layerdrop = 0.0
        self.backbone = Wav2Vec2Model(cfg); d = cfg.hidden_size
        self.layer_w = nn.Parameter(torch.zeros(keep_layers + 1))
        self.proj = nn.Sequential(nn.LayerNorm(d), nn.Linear(d, 256), nn.GELU()); self.pool = AttnStatsPool(256)
        self.head = nn.Sequential(nn.Dropout(0.2), nn.Linear(512, 128), nn.GELU(), nn.Dropout(0.2), nn.Linear(128, 1))
    def forward(self, wav):
        hs = self.backbone(wav, output_hidden_states=True).hidden_states; w = torch.softmax(self.layer_w, 0)
        return self.head(self.pool(self.proj(sum(w[i] * hs[i] for i in range(len(hs)))))).squeeze(-1)

class Detector:
    def __init__(self, folder, device="cpu"):
        self.meta = json.load(open(f"{folder}/detector_config.json")); self.device = device
        self.model = DeepfakeDetector(self.meta["base_model"], self.meta["keep_layers"])
        paths = [f"{folder}/detector_state.pt", f"{folder}/best.pt"]
        path = next((q for q in paths if os.path.exists(q)), None)
        if path is None: raise FileNotFoundError(f"No weights found; expected one of {paths}")
        state = torch.load(path, map_location="cpu")
        if isinstance(state, dict) and "model" in state: state = state["model"]   # best.pt wraps the state dict under 'model'
        self.model.load_state_dict(state); self.model.to(device).eval()
        self.sr, self.win = self.meta["sample_rate"], int(self.meta["window_sec"] * self.meta["sample_rate"])

    @staticmethod
    def mulaw_bytes_to_float(b):   # Twilio Media Streams payload (base64-decoded) -> float32 8 kHz
        u = ~np.frombuffer(b, dtype=np.uint8).astype(np.int32) & 0xFF
        sign, exp, mant = u & 0x80, (u >> 4) & 0x07, u & 0x0F
        mag = (((mant << 3) + 0x84) << exp) - 0x84
        return (np.where(sign, -mag, mag) / 32768.0).astype(np.float32)

    @torch.no_grad()
    def score(self, audio, sr):
        # Returns P(fake) for each window plus the mean. audio: float32 mono array at sample rate sr.
        x = np.asarray(audio, dtype=np.float32)
        if x.ndim != 1 or len(x) == 0 or not np.isfinite(x).all() or not isinstance(sr, (int, np.integer)) or sr <= 0:
            raise ValueError("Expected nonempty finite mono audio and a positive sample rate")
        if sr != self.sr: x = resample_poly(x, self.sr, sr).astype(np.float32)
        if len(x) < self.win: x = np.tile(x, int(np.ceil(self.win / max(len(x), 1))))[: self.win]
        hop = self.win // 2
        starts = list(range(0, len(x) - self.win + 1, hop))
        wins = np.stack([x[s:s + self.win] for s in starts])
        wins = (wins - wins.mean(1, keepdims=True)) / (wins.std(1, keepdims=True) + 1e-7)
        p = torch.sigmoid(self.model(torch.from_numpy(wins).to(self.device))).cpu().numpy()
        return dict(window_scores=p.tolist(), mean=float(p.mean()), max=float(p.max()),
                    is_fake=bool(p.mean() >= self.meta["threshold_1pct_fpr"]))
