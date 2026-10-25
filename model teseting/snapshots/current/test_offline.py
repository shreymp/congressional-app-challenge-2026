"""Run the agent's exact scoring path on WAV files, with no phone call and no LiveKit.

Feeds a file through in 20 ms frames, the way LiveKit delivers audio, and prints what the
agent would publish each second. Use it to time the model on the Mac before a real call.

  python test_offline.py ../melo_everyday_03_en-us_s1.1.wav
  python test_offline.py ../ov2_shrey_everyday_03_en-us_s1.1_t0.3_wm1.wav --phone
  python test_offline.py --mic 15        # record 15 s of YOUR voice from the PC mic, then score it
  DETECTOR=stub python test_offline.py some.wav      # plumbing only, no model

The logit column is log(p / (1 - p)). This model's scores sit extremely close to 1.0, so
p prints as 1.000000 for both real and fake; the logit still shows the difference.
"""
import argparse
import statistics
import json
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

import detector_adapter
from scoring import AudioScoringSession
from risk import logit
from risk_protocol import RiskPublisher

SR = 16000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("wav", nargs="?")
    ap.add_argument("--mic", type=float, metavar="SECONDS", help="record from the default microphone instead of a file")
    ap.add_argument("--phone", action="store_true", help="band-limit to 8 kHz first (crude phone simulation)")
    ap.add_argument("--json-out", help="write the exact versioned app messages for contract replay")
    a = ap.parse_args()

    if a.mic:
        import sounddevice as sd
        sr = 16000
        print(f"Recording {a.mic:.0f} s from the microphone. Talk normally...")
        x = sd.rec(int(a.mic * sr), samplerate=sr, channels=1, dtype="float32")
        sd.wait()
        x = x[:, 0]
        sf.write("mic_test.wav", x, sr)
        print("Saved mic_test.wav")
    elif a.wav:
        x, sr = sf.read(a.wav, dtype="float32", always_2d=True)
        x = x.mean(1)
    else:
        ap.error("give a WAV file or --mic SECONDS")
    if a.phone:
        x = resample_poly(x, 8000, sr); sr = 8000
    x = resample_poly(x, SR, sr).astype(np.float32)
    pcm = (np.clip(x, -1, 1) * 32767).astype(np.int16)

    det = detector_adapter.load()
    elevated, high = detector_adapter.thresholds(det)
    print(f"device={det.device}  thresholds elevated={elevated} high={high}")
    session = AudioScoringSession(det, (elevated, high))
    publisher = RiskPublisher("call-offline", "sip-offline", det.mode)
    messages = [publisher.message(session.payload(0))]

    frame, per_sec, times = SR // 50, SR, []
    for i in range(0, len(pcm), frame):
        now = (i + frame) / SR
        session.push(pcm[i:i + frame].tobytes(), now)
        if (i + frame) % per_sec < frame:
            snapshot = session.snapshot(now)
            if snapshot is not None:
                audio, generation = snapshot
                r = det.score_window(audio)
                session.complete(r, generation)
                times.append(r["infer_ms"])
                s = session.latest["deepfake"]
                print(f"t={now:5.1f}s  p_last={r['p_fake']:.6f}  logit={s['logit_last']:6.2f}  smoothed_logit={s['logit_smoothed']:6.2f}"
                      f"  level={s['level']:9}  infer={r['infer_ms']:.0f}ms")
            messages.append(publisher.message({**session.payload(now), "t": round(now, 2)}))
    if a.json_out:
        Path(a.json_out).write_text(json.dumps(messages, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        print(f"App wire messages saved to {a.json_out}")
    print(f"(for reference: elevated threshold logit = {logit(elevated):.2f}, high threshold logit = {logit(high):.2f})")
    if times:
        print(f"\ninference ms: median {statistics.median(times):.0f}, max {max(times):.0f}"
              f"  (must stay well under 1000 ms to keep up with once-per-second scoring)")
    else:
        print("No eligible window (needs 4 s of contiguous audio with at least 1.5 s of speech).")


if __name__ == "__main__":
    main()
