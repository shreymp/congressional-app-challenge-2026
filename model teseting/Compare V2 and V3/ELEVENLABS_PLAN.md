# Getting ElevenLabs detection back up without losing V3's gains

October 23, 2026. A follow-up to [README.md](README.md). Every number below comes from the saved logits in `results/per_window.csv`; no model was re-run. To reproduce them, run `analysis/elevenlabs_gap.py`.

## Short answer

**Changing the threshold won't get V3 back to 99.6% on ElevenLabs while keeping 2% human false flags. The two models' scores overlap too much on this set for any single threshold to do both.** The real fixes are:

1. Fix how the app turns V3's scores into a call verdict. With V3's supplied thresholds, the app never puts an ElevenLabs call in the "AI" state.
2. Do a targeted V4 fine-tune: ElevenLabs audio in training, plus work on the white-noise weakness.
3. Measure both on recordings that are not these five. Without that, any tuning is fitted to the same data it's graded on.

## What the V2 vs V3 numbers actually show

### 1. V2's 99.6% isn't a target V3 can match at 2% false flags

V2 caught 99.6% of ElevenLabs windows because its threshold also flagged 57% of the human windows. To compare the models fairly, set each one's threshold so it flags the same share of human speech:

| Human windows falsely flagged | V2 catches ElevenLabs | V3 catches ElevenLabs |
|---:|---:|---:|
| 0% | 84.2% | 61.5% |
| ~2% (V3's current operating point) | 84.9% | 81.3% |
| ~5% | 87.4% | 87.8% |
| ~10% | 87.8% | **97.5%** |
| ~16% | 92.1% | **99.3%** |
| 57% (V2's current operating point) | 99.6% | 100% |

At very low false-flag rates the two models are close, with V2 slightly ahead. From about 5% upward, V3 is better. On this set, neither model reaches ~99% detection at 2% false flags. That combination needs a better model, not a different threshold.

### 2. Most of V3's misses come from two causes

V3 misses 58 ElevenLabs windows at its EER threshold:

- **35 of the 58 are in white-noise conditions.** Under white noise, V3 catches 58% of AI windows (V2 catches 99%, but it also flags 52% of humans). V3's own training report shows the same weakness: validation EER is 15.9% at 10 dB noise versus 3.3% on clean audio.
- **The other 23 come from about four stretches of speech, repeated across conditions.** Shrey's first two windows (0–8 s) score 1.3 and 1.8, just under the 2.03 threshold, and every derived condition (8 kHz, μ-law, quiet, clipping, pauses) inherits those misses. Without white noise, V3 catches 88.1% of AI windows with 0% human false flags. V2 catches 100%, with 59.6% human false flags.

### 3. The bigger problem is the app verdict, not the window score

The app doesn't act on single windows. `CallEvidenceEngine` (call-evidence-v1, the default) averages windows over the call. It centers its 35/65 "human/AI" score on the midpoint of the model's two thresholds:

- V2: midpoint 13.75. ElevenLabs windows sit around 25, well above it, so calls go to "AI".
- V3: midpoint (2.03 + 6.00) / 2 = 4.0, with a scale of about 3.2. ElevenLabs windows mostly sit between 4 and 7, so the call score lands around 55–60, below the 65 needed for "AI".

I replayed every speech case through the real engine:

| | ElevenLabs calls → AI | → uncertain | → human | Human calls → human | AI warning ever shown on a human call |
|---|---:|---:|---:|---:|---:|
| V2, supplied thresholds | 27/30 | 3 | 0 | 9/20 | 1/20 |
| **V3, supplied thresholds** | **0/30** | 26 | 4 | 20/20 | 0/20 |
| V3, both thresholds at 2.03 (diagnostic only) | 25/30 | 2 | 3 | 19/20 | 1/20 |

**If V3 is deployed with its current config, ElevenLabs calls will show "uncertain", not "AI".** The third row shows the problem is the mapping, not the model's ability to rank. With the cutoffs moved, V3 sends most ElevenLabs calls to "AI" and still keeps humans as "human". The 2.03 values were picked by looking at this data, so treat that row as proof the lever works, not as the setting to ship.

Without white noise, V3's *call-average* logit separates the classes perfectly on this set: the lowest ElevenLabs case averages 3.99 and the highest human case averages −4.05.

### Caveats that still apply

These are 3 ElevenLabs voices and 2 LibriSpeech speakers, with correlated derived conditions. V3 was trained on other LibriSpeech speakers, so its 2% human false-flag rate is probably optimistic for real callers. No model in this comparison saw ElevenLabs audio in training: V2 and V3 fakes are all MLAAD.

## Goal for a V4 (or a fixed V3)

Measure on a **held-out** set (step 0), not the five current recordings.

| Measure | Must not get worse than V3 | Target |
|---|---|---|
| Human windows falsely flagged | ≤ 2% | ≤ 2% |
| ElevenLabs windows detected | ≥ 79% | **≥ 97–99%** |
| ElevenLabs calls reaching "AI" in the app | — | **100%** |
| Human calls reaching "AI" in the app | 0 | 0 |
| Balanced accuracy / AUC / EER | 88.5% / 0.984 / 7.2% | better |
| Non-speech probes flagged | 0/45 | 0/45 |
| Clean and phone conditions | no drop | no drop |

I can't promise V4 reaches 97–99%. It is a reasonable target once ElevenLabs is in the training data, but only the held-out test will show whether it does.

## Plan of action

### Step 0: Build a held-out set (needed for everything else, about half a day)

- **ElevenLabs:** at least 8–10 voices that are *not* Shrey, Keshav or Azim, using library voices and consented clones. Vary the settings the filenames encode (`sp`, `s`, `sb`) and the model. Use scam-style scripts, 30–60 s each.
- **Human:** at least 8–10 people outside LibriSpeech, ideally older adults, recorded on a phone. Include a few real calls through LiveKit with `RECORD_CALLER_AUDIO=1` and everyone's consent.
- Split **by voice or speaker** into a *calibration* half and a *test* half. Run both through the existing condition set with `compare.py`.
- `model teseting/validation/calibrate.py fit` already requires at least 8 independent sources per class for a release calibration. This step meets that requirement.
- Check ElevenLabs' current terms on using generated audio to train a detection model before step 3. I'm not certain what they allow.

### Step 1: Fix V3's call verdict (a few hours, no retraining, highest priority before Oct 26)

- Fit Platt calibration for V3 on the **calibration half** and write `calibration.json` beside the checkpoint. `detector_adapter.load_calibration` already loads it and refuses one fitted for a different checkpoint. This replaces the midpoint/scale guess that causes the "uncertain" problem.
- Alternative if time is short: pick `THRESHOLD_ELEVATED_LOGIT` / `THRESHOLD_HIGH_LOGIT` (env vars `detector_adapter.thresholds()` already reads) from the calibration half.
- Re-run the call-level replay in `analysis/elevenlabs_gap.py` on the **test half**. Pass condition: every ElevenLabs test call reaches "AI" and no human test call does.

### Step 2: Choose the window threshold deliberately (an hour)

Pick V3's window threshold on the calibration half at the false-flag rate you're willing to accept. The curve in section 1 is the trade-off: about 81% detection at 2% false flags, about 88% at 5%, about 97% at 10%. Changing the threshold alone moves you along that curve. It doesn't fix the gap.

### Step 3: V4 targeted fine-tune from V3 (1–2 days including Colab; the real fix)

Start from `inputs/models/v3/detector_state.pt` and the V3 notebook. Change one thing at a time so you can tell what helped:

1. **Add ElevenLabs fakes** from the training voices only, never the test voices, at about 15–25% of fake samples. Treat that share as a starting value to tune.
2. **Add a noise-consistency loss.** Score a clean and a noisy copy of the same clip and penalize the logit difference. Apply it to both classes so it stays label-blind, as the notebook requires. This targets the 35 white-noise misses directly.
3. **Protect V3's human-side gains.** Keep V3's real-speech mix (LibriSpeech + M-AILABS) unchanged and anchor weights toward V3 (L2-SP). Optionally, distill V2's logits on *fake clips only* to recover its strong AI side. Run that as a separate ablation, because V2 also over-flags humans.
4. **Change model selection.** V3 kept the epoch with the lowest pooled EER, which optimizes the middle of the curve. The gap is at the low-false-flag end. Select on **AI detection at 2% pooled-validation false flags**, with ElevenLabs validation voices included.
5. Recompute the logit thresholds and calibration for V4 on the calibration half. Thresholds must stay with their model: V2's thresholds applied to V3 catch 0% of AI windows.

Suggested runs: (1) alone → (1)+(2) → (1)+(2)+(3). Choose on validation, then score the test half **once**.

### Step 4 (fallback): V2+V3 ensemble

A quick check on this set: scoring `V3 + 0.3 × V2` raises AUC from 0.984 to 0.991 and detection at ~2% false flags from 81% to 90%. That weight was fitted on these same windows, so the gain is optimistic. It also doubles inference per 4-second window. Check latency on LiveKit Cloud before considering it. Use it only if step 3 falls short.

### Step 5: Decide

Re-run `compare.py` with V2, V3 and V4 on the held-out test half. Deploy V4 only if every row of the goal table passes. Keep V3 and its fixed calibration as the rollback, and re-pin `model_integrity.json` for whichever model ships.

## Order given the October 26 deadline

| When | Do | Why |
|---|---|---|
| Today | Step 0 (a small version is fine), Step 1 | Without step 1, a V3 demo shows ElevenLabs calls as "uncertain" |
| Tomorrow | Step 2; start Step 3 run (1) in Colab | A cheap, measurable improvement |
| Only if run (1) passes the held-out test before the deadline | Swap in V4 | Otherwise ship V3 with fixed calibration and describe V4 as next work |

For judges, the honest version is the stronger story: V3 cut false alarms from 57% to 2%, you found and fixed the verdict mapping, and you measured on held-out voices.
