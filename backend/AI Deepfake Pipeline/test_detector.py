"""Test the CAC deepfake detector on audio files.

Usage (run from this folder, inside your venv):
  python test_detector.py clip1.wav clip2.wav          # just print scores
  python test_detector.py --folder test_audio          # test_audio/real/*  and  test_audio/fake/*  (labeled by folder)
  python test_detector.py --folder test_audio --phone  # also degrade audio to 8 kHz first (rough phone-line simulation)

Needs: torch transformers numpy scipy soundfile
First run downloads the facebook/wav2vec2-xls-r-300m config from Hugging Face (internet needed once).
"""
import argparse, glob, os, sys, time
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly
from inference import Detector

HERE = os.path.dirname(os.path.abspath(__file__))
EXTS = (".wav", ".flac", ".ogg", ".mp3")


def load(path, phone):
    x, sr = sf.read(path, dtype="float32", always_2d=True)
    x = x.mean(axis=1)                       # mono
    if phone:                                # crude 8 kHz bandwidth limit, NOT a real codec
        x = resample_poly(x, 8000, sr).astype(np.float32); sr = 8000
    return x, sr


def auc(pos, neg):                           # P(fake score > real score), ties count half
    pos, neg = np.asarray(pos), np.asarray(neg)
    return float(((pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()) / (len(pos) * len(neg)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--folder", help="folder containing real/ and fake/ subfolders")
    ap.add_argument("--phone", action="store_true")
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--weights-dir", default=HERE)
    a = ap.parse_args()

    items = [(f, None) for f in a.files]
    if a.folder:
        for label in ("real", "fake"):
            for f in sorted(glob.glob(os.path.join(a.folder, label, "*"))):
                if f.lower().endswith(EXTS): items.append((f, label))
    if not items: sys.exit("No audio files given.")

    det = Detector(a.weights_dir, device=a.device)
    thr = det.meta["threshold_1pct_fpr"]
    print(f"Config threshold (1% FPR) = {thr!r}  |  phone-simulation: {a.phone}\n")
    print(f"{'file':45} {'label':6} {'mean':>9} {'max':>9} {'secs':>6} {'infer_s':>8}  is_fake")
    rows = []
    times, durations = [], []
    for f, label in items:
        x, sr = load(f, a.phone)

        t0 = time.perf_counter()             # time only the inference call
        r = det.score(x, sr)
        dt = time.perf_counter() - t0

        times.append(dt); durations.append(len(x) / sr)
        rows.append((label, r["mean"]))
        print(f"{os.path.basename(f)[:45]:45} {str(label):6} {r['mean']:9.6f} {r['max']:9.6f} {len(x)/sr:6.1f} {dt:8.3f}  {r['is_fake']}")

    print(f"\nInference time: total {sum(times):.2f}s over {len(times)} clip(s), "
          f"mean {np.mean(times):.3f}s/clip, min {min(times):.3f}s, max {max(times):.3f}s")
    print(f"Real-time factor (inference time / audio length): {sum(times) / sum(durations):.3f}  (below 1.0 = faster than real time)")
    if len(times) > 1:
        print(f"Note: the first clip ({times[0]:.3f}s) often includes one-time warm-up; "
              f"mean excluding it: {np.mean(times[1:]):.3f}s/clip")

    real = [m for l, m in rows if l == "real"]; fake = [m for l, m in rows if l == "fake"]
    if real and fake:
        print(f"\nlabeled clips: {len(real)} real, {len(fake)} fake")
        print(f"AUC (ranking only, threshold-free): {auc(fake, real):.3f}")
        for name, t in (("config 1%-FPR threshold", thr), ("config EER threshold", det.meta["threshold_eer"]), ("0.5", 0.5)):
            tpr = np.mean([m >= t for m in fake]); fpr = np.mean([m >= t for m in real])
            print(f"at {name:26} (t={t:.7f}): catches {tpr:.0%} of fakes, false-alarms on {fpr:.0%} of real")
        print("\nWith few clips these percentages are noisy; treat them as a sanity check, not an accuracy number.")


if __name__ == "__main__":
    main()