# Independent audit and improvement plan: voice deepfake pipeline

Written October 22, 2026. This plan is based only on the evaluation in this folder (`README.md`, `regression_report.md`, `source_audit.md`, `results/`, `snapshots/`) and a read of the local checkout. It does not use `IMPROVEMENT_PLAN.md`. No production code, thresholds or weights were changed.

## What I checked

- Recomputed the report's headline numbers from `results/summary.csv` and `results/per_window.csv`. Every value I spot-checked matches: first-AI times, the old version's false AI on the two human controls (8.98 s and 13.00 s), the 10 dB final score of 63.3, zero windows for the −20 dB clip, and 20.01 s of incorrect Human in the 120 s prefix case.
- Read the baseline and updated `audio_window.py`, `scoring.py`, `risk.py`, `agent.py`, `detector_adapter.py`, `model/inference.py`, `model/detector_config.json`, and the Swift `DeepfakeAssessment.swift` and `ProductionCallView.swift`.
- Compared the local checkout byte for byte against both snapshots.
- Pulled the raw per-window logits and speech weights to separate model problems from gating problems and aggregation problems.

## Bottom line

The report's conclusion holds: the cumulative aggregator removes false AI headlines on the two human controls, but it handles speaker changes badly and misses quiet audio. The per-window data shows a deeper problem underneath the aggregator, though. On real human speech, the detector's raw scores fall between its own two configured thresholds, and sometimes above both. Noise pushes AI scores down into that same range. No averaging rule can reliably separate two classes whose individual window scores overlap.

The right order of work is:

1. Get the evaluated code onto your branch.
2. Fix the evaluation set so it can tell model problems from recording confounds.
3. Fix the speech gate.
4. Recalibrate the thresholds in logit space.
5. Rebuild the headline aggregator around current speech.
6. Fix what the senior sees.
7. Retrain only if calibration is not enough.

## Findings the report already establishes

- The neural model, checkpoint, adapter, per-window normalization and thresholds are identical in both versions. Every behavior difference comes from windowing and aggregation.
- The updated version removes false AI headlines on both human controls. It also keeps evidence across long silence.
- The updated version never scores the −20 dB clip, and it misses AI at 10 dB SNR. At 10 dB, both aggregators fail on the same windows.
- Whole-call memory delays detection after a long human introduction. In the 120 s prefix case, Human stays on screen alongside an active recent-AI warning for 8 s. After an AI-to-human switch, the AI headline stays up for the full 40 s of human speech.
- The recent warning has its own false alarm: 8 s during a repeated human introduction.

## New findings

### N1. Your branch runs the baseline code, not the updated version

`audio_window.py`, `scoring.py`, `risk.py` and `agent.py` in `backend/AI Deepfake Pipeline/LiveKit Setup/` are byte-identical to `snapshots/baseline/`. The local checkout also lacks several pieces of the updated version:

- `recording_notice.py`
- `CallEvidenceEngine`
- any `recentAI` or `call-evidence-v1` handling in `ios/Callma`

The `improved-ui` checkout has no git remote configured. As things stand, the app you would demo is the version that falsely labeled both human controls AI.

### N2. Real human speech scores above the detector's own thresholds

In logit space, the configured thresholds are 11.56 ("EER") and 15.94 ("1% FPR").

| Human control | Version | Windows | Median logit | ≥ 11.56 | ≥ 15.94 |
|---|---|---:|---:|---:|---:|
| LibriSpeech 1320 | updated | 10 | 15.41 | 8 | 4 |
| LibriSpeech 6930 | updated | 10 | 12.54 | 6 | 1 |
| Both speakers | baseline (overlapping windows) | 72 | — | 54 | 18 |

In the updated version, 5 of 20 human windows exceed a threshold named for a 1% false-positive rate. These are two speakers and the windows are correlated, so this is not a rate estimate. It is still far from 1%.

In the aggregator's own units, the speech-weighted mean evidence at call end is **+0.16** for speaker 1320 (final score 53.9) and −0.52 for speaker 6930 (final score 37.2). The Human cutoff is −0.62 and the AI cutoff is +0.62, so both controls end in the Inconclusive band, and speaker 1320 sits on the AI side of center. That is why neither control settles on Human. The 0–100 score is centered in the middle of the human cluster.

### N3. The "1% FPR" threshold is a float32 rounding artifact

The value 0.9999998807907104 is exactly 1 − 2·2⁻²⁴. That is the second-largest float32 number below 1.0; only 0.99999994 and 1.0 lie above it. The EER threshold is 1 − 160·2⁻²⁴.

The most likely explanation is that the threshold search ran on float32 sigmoid probabilities that had saturated. If so, the true 1%-FPR point in logit space is unknown; all we know is that it is at least 15.94. The comment in `detector_adapter.py` already notes that float32 rounds everything above about 0.99999994 to 1.0.

`CallEvidenceEngine` derives its center (13.75) and scale (3.54) from these two values, so the whole 0–100 score inherits the problem. *This is an inference from the numbers; the training notebook would confirm it.*

### N4. The validation error rate is 18 times the test error rate

`detector_config.json` reports:

- validation EER: 0.108
- test EER, clean: 0.0059
- test EER, phone: 0.0172

A validation set that much harder than the test set usually means one of two things. Either the test set shares speakers, TTS systems or recordings with the training data, or the validation set comes from a different distribution. Until that is explained, the test EER and AUC should not be described as expected real-world performance, including to CAC judges. The training recipe is not in the repo.

### N5. Degradation pushes AI scores into the human range, and the human controls were never degraded

Median logits of the updated version's windows:

| Clip | Median logit |
|---|---:|
| AI, clean | 25.95 |
| AI, 30 dB SNR | 21.92 |
| AI, 20 dB SNR | 19.42 |
| AI, G.711 | 21.77 |
| AI, 10 dB SNR | **15.51** |
| Human 1320, clean | **15.41** |
| Human 6930, clean | 12.54 |

At 10 dB SNR, the AI clip scores the same as clean human speech. `evaluate.py` applies `conditions()` only to the AI clip, so the human controls were tested clean only.

That leaves the key question open. If noise and codecs shift human logits by the same amount, a calibration can fix this. If they don't, the model needs retraining. Either way, the error runs in the dangerous direction: a real phone line pushes AI speech toward "Human."

### N6. The speech gate fails in both directions

The gate is a fixed RMS ≥ 0.01 (about −40 dBFS) per 20 ms frame.

**Too strict for quiet speech.** The AI clip's overall RMS is 0.0697 (about −23 dBFS). At −20 dB it drops to about −43 dBFS, so too few frames pass. The model handles quiet audio fine: each window is z-normalized before inference, so the model ignores volume. The baseline version, which did score the −20 dB clip, produced a median logit of 25.1, the same as the original.

**Too loose under noise.** At 10 dB SNR the noise alone has RMS ≈ 0.022, which is above the gate. Every frame counts as speech: all nine window weights are 1.00, compared with 0.52–0.77 on the clean clip. Speech-fraction weighting and the 1.5 s voiced-speech requirement stop meaning anything. Steady noise, hold music or a TV in the background would be submitted to the model as "speech."

### N7. The test set has confounds that could make the model look better or worse than it is

- **Codec.** The AI clip is a 128 kb/s MP3. The human controls are lossless FLAC.
- **Speaker.** The filename `..._shrey_ivc_...` suggests an ElevenLabs instant voice clone of you. The human controls are two other men reading audiobooks.

So whatever separates the classes in this test could be MP3 encoding, microphone and room, speaker identity, or reading style, rather than synthesis itself. *I am inferring "ivc" = instant voice clone from the filename; please confirm.*

### N8. The cost of whole-call memory, quantified

The headline is a speech-weighted mean of bounded evidence over the entire call. Suppose a call starts with N human windows of mean evidence b_h, followed by AI windows of mean evidence b_ai. Then reaching the AI cutoff of 0.62 takes about

k ≈ N · (0.62 − b_h) / (b_ai − 0.62) AI windows.

Plugging in the recorded logits and weights for the 120 s prefix case (N = 30, b_h = −1.13, b_ai = 3.45) gives **18 AI windows, about 72 s of AI speech**. The AI clip is 38 s long. The report's "never reaches AI" is built into the design; it is not a near miss.

### N9. Evidence arrives only every 4 s, and the rules count updates instead of seconds

The updated version scores distinct, non-overlapping 4 s windows. That gives one evidence point per 4 s of audio, even though inference took about 20 ms per window on MPS. The timing rules are all written as update counts:

| Rule | Setting | Effect |
|---|---|---|
| Recent warning | last 5 windows (~20 s), at least 3 needed | no warning sooner than ~12 s after a switch |
| First verdict | `MIN_SEGMENTS = 2` | no verdict before ~8 s |
| State change | 2 qualifying updates | ~8 s |

Because these are counts, changing the window rate would silently change every time constant.

### N10. There are no non-speech controls

The evaluation includes no silence, noise-only, music, DTMF tone or crosstalk inputs. Each window is z-normalized, so a near-silent window of hiss is scaled up to unit variance before the model sees it. Nobody knows what the model outputs on these inputs. That has to be measured before the gate is loosened.

### N11. Outside the report's scope

Voice evidence alone never triggers protective action. `combine()` only reaches "prevention" when the transcript score is ≥ 0.8 **and** the voice level is high, and the report did not evaluate the transcript side. The recent-AI warning also renders as caption-size text under the headline. Both matter for older users, but this report has no evidence on either.

## Symptom → cause → fix

| Symptom in the report | Root cause | Fixed in |
|---|---|---|
| Old version falsely labels both human controls AI | Baseline code; human logits above the thresholds (N2) | Phase 0, Phase 3 |
| Updated version never settles on Human for clean human speech | Score center sits inside the human cluster (N2, N3) | Phase 3 |
| −20 dB AI clip never scored | Fixed −40 dBFS gate (N6) | Phase 2 |
| 10 dB AI clip missed by both aggregators | Noise lowers AI logits into the human range (N5); gate counts noise as speech (N6) | Phases 1, 2, 3, then 6 if needed |
| Human→AI switch takes too long; Human shown alongside a warning | Unlimited whole-call memory (N8); 4 s cadence and count-based rules (N9) | Phases 4, 5 |
| AI headline stays up through 40 s of human speech | Same as above | Phases 4, 5 |
| False recent warning on a human introduction | Human windows reach 17+ logits (N2) | Phase 3, then Phase 4 |

## Plan

### Phase 0: Put the evaluated code on your branch (blocks everything else)

1. Add the GitHub remote. Fetch `shrey` (`ec2f4dd`). Create a new branch off `improved-ui` and merge `shrey` into it.
2. Resolve the `Callshield/` → `Callma/` rename. Git rename detection should map most files. Check these by hand:
   - `DeepfakeAssessment.swift`
   - `ProductionCallView.swift` (expect conflicts with the Paper & Midnight UI revamp)
   - `PhoneSessionState.swift`
   - `PhoneCallCoordinator.swift`
   - the test targets and `Fixtures/deepfake-wire.json`
3. Run the backend tests: `test_integration`, `test_cumulative`, `test_agent_integration`, `test_recording_notice`, `test_offline` and `test_senior_ring`. Then run the iOS unit and UI tests.
4. Point `evaluate.py` at the merged backend instead of the snapshots. Confirm the logits and decisions are identical to `results/summary.csv`.

**Done when:**
- the merged detection core matches `snapshots/current`
- all tests pass
- the harness reproduces the saved results

### Phase 1: Fix the evaluation so it can find the real cause

1. **Matched human controls.** Apply the same nine degradations to both human controls. Also encode the human controls as 128 kb/s, 44.1 kHz MP3 before resampling, the same way the AI clip was produced.
2. **Same-speaker pair.** If the clip is a clone of you, record yourself reading the same script on the same microphone and export it the same way. Real speech versus a clone of the same person is the cleanest test of whether the model detects synthesis.
3. **More AI sources.** Add several ElevenLabs voices, both premade and cloned, plus at least two other TTS engines. Add more human speakers, including older adults, women and natural conversation.
4. **Non-speech controls.** Add silence, white and pink noise, hold music, TV and background chatter, and DTMF tones, each at several levels.
5. **Real phone-path recordings.** With everyone's consent, place calls through the live system with `RECORD_CALLER_AUDIO=1`. The agent then saves exactly the 16 kHz caller audio the model sees. Record human speakers, and AI clips played through a phone speaker. This is the single biggest improvement to the evidence, and it doubles as the real-world testing that CAC judges weight heavily.
6. **Harness changes.**
   - Always save per-window logits.
   - Replace the paths hard-coded to `~/Downloads` with parameters.
   - Group every derived clip under its source recording.
   - Split the data by source into a dev set for tuning and a held-out set that is evaluated only once.
   - Write each run to a new dated folder.

**Done when:**
- there is a per-window logit table for human and AI audio under every condition
- you can answer whether degradation moves human logits the same way it moves AI logits

### Phase 2: Fix the speech gate

1. Replace the fixed −40 dBFS gate with one of two options:
   - an adaptive gate that tracks the noise floor (for example, a low percentile of frame RMS over the last few seconds) and counts a frame as speech when it is above floor + margin and above an absolute minimum; or
   - a trained voice-activity detector such as WebRTC VAD or Silero VAD. *Verify the current package and API before adopting either.*
2. Set each window's weight to the fraction of frames the new gate marks as speech, so 10 dB noise no longer produces a weight of 1.00.
3. Keep contiguous audio, pause retention and the clipping check.
4. When no window qualifies, report a reason: too quiet, too noisy, no speech, or clipped.
5. Don't add gain normalization for the model's sake. Each window is already z-normalized.

**Done when:**
- the −20 dB AI clip and quiet human speech both reach the model
- 10 dB noise windows get weights close to the clean clip's speech fraction
- the silence, noise and music controls produce no verdict
- the existing pause and clipping tests still pass

### Phase 3: Recalibrate the detector's scores (a model fix without retraining)

1. Get the training notebook and the validation set. Recompute the thresholds from float64 raw logits, not float32 probabilities. Find out why validation EER is so much worse than test EER.
2. Fit a two-parameter calibration on the Phase 1 dev data (phone-path recordings plus matched controls): p = σ(a·z + b), known as Platt scaling. With only two parameters, the risk of overfitting is low. Replace the center and scale in `CallEvidenceEngine` with the calibrated log-odds.
3. Set error budgets first, such as false warnings per human call and missed AI calls. Then choose the operating points on dev data, and evaluate on the held-out set once.
4. Store the thresholds and calibration together with the checkpoint hash.

**Done when:**
- thresholds and calibration are in logit space, documented, and derived from dev data
- a held-out report gives per-call false warnings and misses, with counts

If Phase 1 shows that human and noisy-AI logits overlap under matched conditions, calibration can't fix it. Go to Phase 6.

### Phase 4: Rebuild aggregation around current speech

1. **Current-speech engine.** Use an exponentially decayed, speech-weighted mean of calibrated evidence, with the half-life measured in seconds of speech. Try candidates from 6 to 15 s and pick one on dev data. Decay only when new speech arrives, so silence never drifts the assessment toward Human.
2. **Faster evidence.** Score overlapping 4 s windows every 1–2 s. Weight each window by the fraction of new speech it adds, so the total weight per second of audio stays the same; this avoids the baseline's overcounting. Measure latency on the deployed hardware first (Phase 7).
3. **Rules in seconds.** Rewrite the minimum-evidence rule, the hysteresis and the recent-warning rule in seconds of speech instead of update counts.
4. **Separate entry and exit speeds.** Decide on dev data whether entering AI should be faster than leaving it, measuring both missed detections and false warnings.
5. **Keep history separate.** Keep the whole-call mean as a secondary "call summary." Add a persistent event: "AI-like voice detected earlier, at mm:ss."
6. **Design target.** With a half-life h, the weight of earlier human evidence halves every h seconds of new speech. Switch time should then depend on h, not on the length of the introduction. Today it is about 72 s for a 120 s introduction. This is a goal to verify, not a measured result.

**Done when:**
- in the prefix cases, the delay to reach AI after the switch is within one window whether the introduction is 60 s or 120 s
- after an AI→human switch, the assessment recovers
- the human controls and clean AI clip are no worse than the updated version on dev data
- the held-out set confirms all of the above

### Phase 5: Fix what the senior sees

1. Drive the headline from the current-speech engine. Never show "Human" while a fresh AI warning is active.
2. Make the warning headline-level: large text, with a plain action such as "Hang up and call them back on a number you know."
3. Label the whole-call score clearly, or move it to the caregiver and history views.
4. Add the new fields as `call-evidence-v2`: `current_state`, `current_score`, `call_score`, evidence end time, `quality_reason` and events. Make Swift decode both v1 and v2.

**Done when:**
- there are fixtures for Human plus warning, stale evidence and each quality reason
- VoiceOver text matches the screen
- this has been tested on a physical iPhone

### Phase 6: Retrain, only if Phases 1 and 3 show it is needed

Retrain if either of these holds: matched human and AI audio still overlap under phone conditions after calibration, or real speech and a clone of the same speaker are not separated.

1. **Augmentation, applied equally to both classes:**
   - G.711 μ-law and A-law
   - low-bitrate Opus and MP3
   - 300–3400 Hz band-limiting
   - real recorded noise at 0–20 dB SNR
   - level changes of ±20 dB
   - clipping, reverb and packet loss

   If only one class gets degraded, the model learns "degraded means human," which matches what N5 shows.
2. **Hard negatives.** Add clean read human speech and the kinds of speakers the current model flags.
3. **Clean splits.** Split by speaker and by TTS system. Resolve the validation/test gap. Compute thresholds from float64 logits.
4. **Evaluation and versioning.** Evaluate on the Phase 1 held-out set and report results per condition. Version the checkpoint, calibration and aggregation together.

### Phase 7: Verify the live path

1. Measure inference latency on the deployed setup (the LiveKit Cloud agent calling the loopback detector service that `RemoteDetector` expects, if that is how it is deployed) before raising the scoring rate. The ~20 ms figure was measured on MPS and won't carry over.
2. Place end-to-end calls and measure the time from answering to the first verdict, including the recording notice.
3. Run the full XCTest and simulator suites, which the report did not run.

## Guardrails

- Never tune a cutoff on the 18 report cases. Use them only as dev and regression checks.
- Never count overlapping windows as independent evidence.
- Never boost gain before the gate.
- Never present the config's test EER or AUC as real-world performance.
- Always keep raw logits in the logs.

## Questions I need answered

1. Is the ElevenLabs clip a clone of your voice?
2. Where are the training notebook and validation data? Were the thresholds computed on float32 probabilities?
3. Was LibriSpeech (any split) or LibriTTS used for the "real" class in training?
4. What hardware runs the deployed detector?
5. Which GitHub repo holds `shrey`? Can I merge it into a new branch off `improved-ui`?

## Dependency order

| Phase | Depends on | Unblocks |
|---|---|---|
| 0: merge the evaluated code | remote access | everything |
| 1: evaluation set | 0 | 2, 3, 4, 6 |
| 2: speech gate | 1 (non-speech controls) | 3, 4 |
| 3: calibration | 1, training notebook | 4, 6 decision |
| 4: aggregation | 2, 3 | 5 |
| 5: display and contract | 4 | release |
| 6: retraining | 1, 3 show overlap | 3 again (recalibrate) |
| 7: live path | 0 | 4 (scoring rate), release |
