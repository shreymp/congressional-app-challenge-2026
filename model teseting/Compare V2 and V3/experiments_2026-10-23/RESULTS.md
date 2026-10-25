# Improving ElevenLabs detection without new voices — experiments

October 23, 2026. Follow-up to [../README.md](../README.md) and [../ELEVENLABS_PLAN.md](../ELEVENLABS_PLAN.md). No new recordings, no retraining, no production files changed.

## Recommendation

**Re-centre V3's call verdict. It's a config-only change with no extra compute, and it's the only option that clearly helped without a new risk.**

```sh
THRESHOLD_ELEVATED_LOGIT=0.046875
THRESHOLD_HIGH_LOGIT=4.015625
```

`detector_adapter.thresholds()` already reads these two variables. Only `CallEvidenceEngine` and `CurrentEvidenceEngine` use them, to set where the call score is centred and how spread out it is. This pair centres the call score on V3's own validated EER threshold (logit 2.03, from its training validation, not from these recordings) instead of on the midpoint of its two thresholds (4.02). The spread stays the same. The model, its window thresholds, and every number in the README are unchanged.

| App-level result (call replay, 30 ElevenLabs + 20 human cases) | V3 now | V3 re-centred |
|---|---:|---:|
| ElevenLabs calls ending **"AI"** | **0** | **22** |
| ElevenLabs calls ending "human" (false reassurance) | 4 | **0** |
| ElevenLabs calls showing the live AI warning at some point | 8 | 23 |
| Human calls ending "AI" | 0 | 0 |
| Human calls ending "uncertain" | 0 | 1 (speaker 1320, 10 dB white noise) |
| Non-speech probes (DTMF, music, noise) ending "AI" | 0 | 0 |
| First warning, AI→human and human→AI switch clips | 28 s / 44–148 s | 20 s / 36–140 s |

All 21 non-noise ElevenLabs calls now end "AI", plus one white-noise call. The 8 that don't reach "AI" are all white-noise calls; they now end "uncertain", where before 4 of them ended "human".

**Main risk:** a call now reaches "AI" when its average window logit is ≥ about 4.0, down from about 6.0. In V3's own validation, 5% of real-speech windows pooled across all conditions scored above 3.9. Background music was the hardest case: the real-speech median was 1.7 and the 95th percentile was 6.2. Before relying on this, run at least one real human call with a TV or music in the background.

To reproduce the table: `python3 recentre_check.py`.

## Everything tried

Window numbers are on the 474 speech windows. "Matched FP" places each method's threshold at the same share of human windows flagged, so methods with different score scales can be compared. LORO means leave-one-recording-out: anything fitted was fitted on 4 recordings and scored on the 5th. With only 2 human speakers, LORO false-flag rates are noisy for every method, including the baseline.

| Method | AUC | EER | ElevenLabs detected at ~1.5% / 5% / 10% FP | Non-speech flagged | Cost | Verdict |
|---|---:|---:|---|---:|---|---|
| V3 as is | 0.984 | 7.2% | 72.7 / 84.9 / 97.1% | 0/55 | 1× | baseline |
| **+ re-centred call verdict** | same | same | same (window level unchanged) | 0/55 | 1× | **recommended** |
| + 2-s hop, average each window with its half-shifted neighbours | 0.989 | 5.7% | 73.4 / 91.0 / 99.3% | not re-run | ~2× inference | small real gain; optional later |
| V3 on 8 kHz band-limited input | 0.988 | 5.7% | 78.4 / 93.5 / 96.8% | 0/55 | 1× | rejected: conflicts with V3's validation (phone EER 9.6% vs clean 3.3%); call level worse (2 AI calls → "human") |
| Denoised input (noisereduce) | 0.925 | 14.3% | 54.7 / 81.3 / 83.8% | 0/55 | 1× + denoise | rejected: worse |
| Average of original + denoised | 0.977 | 9.1% | 82.7 / 88.1 / 92.5% | 0/55 | 2× | rejected |
| V2+V3 score fusion (V3 + 0.3·V2) | 0.991 | 5.1% | 90.3 / 95.0 / 97.5% | **35/55** | 2× | rejected for now: brings back V2's non-speech false alarms with the default fixed gate; only viable with `SPEECH_GATE=silero`, which isn't validated yet |
| Few-shot correction layer on V3 features | — | — | LORO, no noise: 99% detected / 0% FP at best setting | — | 1× | rejected: results swing widely with settings (LORO false flags 11–53%); learned from 3 voices; unknown effect on other TTS systems |

At V3's supplied window threshold (2.03), the 2-s hop averaging raises ElevenLabs detection from 79.1% to 80.2%, and from 88.1% to 92.3% without noise. Human false flags stay at 2.0%.

## What the experiments showed

- **Noise is the whole remaining problem at window level.** Without the white-noise conditions, plain V3 already separates the classes perfectly on this set: the lowest ElevenLabs window scores −0.23 and the highest human window −1.05. Every false flag that appears when you lower the threshold comes from noisy human audio. Lowering the window threshold isn't recommended for that reason. Also, the human controls are LibriSpeech, which is in V3's training corpus, so real callers will probably score higher than these two speakers.
- **Nothing tried without new data fixes the noise weakness.** Denoising made it worse. Fusion helped, but only by bringing in V2's habit of flagging everything, non-speech included. Fixing noise needs a retrain (step 3 of ELEVENLABS_PLAN.md: a noise-consistency loss), and that doesn't need new ElevenLabs voices. It can use the 3 recordings you already have plus noise augmentation, with the limitation that results are then measured on the same voices.

## Files

| File | Purpose |
|---|---|
| `recentre_check.py` | Reproduces the recommendation table from saved logits (no model run) |
| `common.py` | Shared metrics, LORO harness, call replay with the app's `risk.py` |
| `exp_no_inference.py` | Baseline, LORO calibration, V2+V3 fusion → `out_no_inference.json` |
| `infer.py`, `run_variants.py` | CPU inference; 8 kHz and denoise input variants → `results_variants.json` (via `analyze.py`) |
| `regen.py`, `run_shift.py` | Rebuild condition audio and score at a 2-s hop |
| `head_adapt.py` | Few-shot correction layer (LORO) → `results_head*.json` |

Run the scripts from this folder. Inference used CPU float32 and reproduces the saved MPS logits to within 5e-5. Rebuilt audio differs slightly from the Mac decode (MP3 decoder), and one borderline call flips between the two, so treat ±1 call as noise. Caches (`cache/`) were not saved; the scripts recreate them (about 25 min of CPU).
