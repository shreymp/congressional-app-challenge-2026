# Voice evidence contract and staged rollout

The `schema: 1` envelope and authenticated sender/room/caller/stream/sequence rules stay intact. `deepfake.method` retains `call-evidence-v1` by default: its state and score are the frozen cumulative, speech-weighted whole-call heuristic. Scores are not calibrated probabilities and do not verify identity or call safety. Transcript/scam evidence stays separate.

Every scoring-session packet adds `evidence_version: call-evidence-v2`, `scoring_method` (the actually enabled policy), and `assessment`. These additions do not reinterpret v1's score. Baseline packets without a method remain supported by updated Swift. A v2 current policy is emitted only when both `CURRENT_EVIDENCE_ENABLED=1` and `SCORING_WIRE_VERSION=call-evidence-v2` explicitly target clients known to support v2. There is no automatic capability negotiation in this implementation; deploy in an isolated version-targeted worker/dispatch cohort. Never send enabled v2 policy to an unverified old client.

| Assessment field | Meaning |
|---|---|
| `current_state` | `analyzing`, `human`, `uncertain`, `ai`; candidate finite-horizon state |
| `current_score` | Nullable 0–100 heuristic for that horizon; not a probability |
| `whole_call_score` | Nullable v1 cumulative heuristic, retained after silence/failure |
| `evidence_start_sec`, `evidence_end_sec` | Paired finite, nonnegative interval; retained as a dated interval after expiry |
| `evidence_age_sec` | Time since the latest submitted audio ended, not heartbeat or inference completion |
| `freshness` | `none`, `fresh`, `stale`; independent of availability |
| `analysis_status` | `analyzing`, `available`, `unavailable`, `stale` |
| `quality_reason` | Null or `insufficient_speech`, `audio_too_quiet`, `audio_too_noisy`, `audio_distorted` |
| `status_reason` | Null or `insufficient_speech`, `inference_pending`, `inference_timeout`, `inference_failed`, `evidence_stale` |
| `current_warning` | Qualified current warning; v1 uses time-limited legacy warning, v2 uses candidate warning |
| `historical_warning_events` | At most 64 objects `{id: String,start_sec,end_sec,current: Bool}`; no audio or transcript |
| `pending_state` | Nullable target while the candidate's usable-speech hysteresis runs |
| `score_kind` | Always `heuristic` |

Notice-stage status packets use `reason: recording_notice_pending | recording_notice_failed` before scoring starts. Missing model emits `unavailable`; newer clients may show that as detector unavailable. Notice failure disables caller streams, transcription and optional recording.

All times share the agent's connection-relative monotonic origin. This is the agent's room connection, not the iPhone's connection clock or the carrier's answer timestamp. Audio evidence ends at submission; completed work carries that interval, so a late result cannot look newly fresh. Swift starts its own 15-second deadline from its own connected-call event. `timing` and `counters` expose metadata only, correlated by envelope stream and increasing generation/window number (`window_id`); monotonic times must not be subtracted across devices. End-to-end measurement still requires an explicit clock alignment method and actual phone-path packet/display captures.

An inference older than ten seconds is shown as unavailable. Work is not duplicated while its uncancellable thread runs. When it returns, its generation is retired and that late result does not add evidence. An explicit later inference can recover. Shutdown invalidates all pending work. v2 expiry emits a status with `previous_deepfake` for history, while its current score becomes null and state analyzing. Silence never creates Human evidence. v1 risk fields remain unchanged for old decoders; updated presentation uses additive freshness to date them.

# Candidate configuration

Defaults preserve distinct four-second inputs, the fixed `.01` RMS gate, v1 aggregation, existing checkpoint, preprocessing and thresholds. `ScoringConfig` is immutable and serialized in packets/evaluation runs. Its API supports horizon, mean/decay, half-life, minimum usable speech and asymmetric entry/recovery durations; defaults are experiment settings without held-out validation. The environment exposes only the documented cohort controls:

```sh
# Development cohort only, after pairing an explicitly v2-capable client:
CURRENT_EVIDENCE_ENABLED=1 SCORING_WIRE_VERSION=call-evidence-v2 CURRENT_HORIZON_SEC=16 CURRENT_EVIDENCE_MODE=mean
# Independently enable quiet eligibility for development replay:
QUIET_ELIGIBILITY_ENABLED=1
```

`quiet_enabled` uses 20ms-frame noise-floor, spectral flatness, telephony-band and crest estimates, retaining contiguous waveform and pauses. It is not a trained/validated VAD. `voiced_sec` is explicitly marked `voiced_sec_kind: gate_estimate`; quality diagnostics include eligible duration, energy, floor estimate and clipping. Thresholds have not been lowered to fit report cases. White noise/silence/tone controls are useful unit/development checks; they do not establish safety on music, television, crosstalk or unseen noise.

Mean and speech-decayed alternatives both trim at the configured wall-clock horizon. Only retained evidence determines candidate state/hysteresis. Entry/recovery rules use new estimated speech seconds; a separate two-distinct-segment support minimum remains explicit. Silence ages evidence to stale and keeps historical events. Production still submits distinct windows. If an experiment overlaps inputs, its `weight` must estimate speech in the genuinely new tail, not the whole input. The caller must supply this correctly; the engine cannot infer speech location from one aggregate weight.

The benchmark has already found an increased warning on a reused human control with the current candidate. Candidate warnings and history do not leak into the default v1 alerts. This is a development rejection signal, not a released improvement. Select settings only from independent development/calibration evidence and freeze release budgets before held-out testing.

## Speech gate, digital-silence guard and calibration (added 2026-10-22, second pass)

```sh
SPEECH_GATE=silero            # trained VAD (livekit-plugins-silero 1.8.8); default "fixed"
DIGITAL_SILENCE_MAX_SEC=.2    # default; "off" disables the guard
CALIBRATION_PATH=...          # optional; default calibration.json beside the checkpoint
ALLOW_DEV_CALIBRATION=1       # needed to use a calibration file whose status is "development"
THRESHOLD_ELEVATED_LOGIT=... THRESHOLD_HIGH_LOGIT=...   # logit-space overrides (float64)
```

- **Digital-silence guard (on by default, every gate).** A window containing more than 0.2 s of exact digital silence (|sample| <= 2 LSB) is not submitted. In run `2026-10-22-factorial-candidates-v2`, windows of 2 s inserted digital silence plus 2 s of LibriSpeech speech scored logits 31.3 and 33.8, above every clean AI median. The wire reason stays `insufficient_speech`; `quality.quality_detail` says `digital_silence_gap` and `quality.digital_silence_max_run_sec` gives the run length. Check real LiveKit caller audio (`RECORD_CALLER_AUDIO=1`, with consent) for how often exact-zero runs occur before relying on coverage.
- **Silero gate (opt-in).** Development checks: 0% of frames marked speech for silence, white and low-pass noise, DTMF, a four-tone chord and a synthetic melody; about 85-89% of frames kept for the two LibriSpeech controls clean, at -20 dB, at 10/20 dB SNR and band-limited to 8 kHz; about 0.07 ms per 32 ms chunk on the test VM. Not yet replayed through the deepfake model (use `model teseting/benchmark/configs/development_silero.json`). Real music with vocals, TV and crosstalk are untested. The worker validates the gate at startup.
- **Calibration (off unless a file exists).** `model teseting/benchmark/calibrate.py` fits Platt scaling (calibrated log-odds = a·logit + b) with source-balanced weights and leave-one-source-out checks, and writes a file bound to one checkpoint SHA-256. The engines then use center = -b/a and scale = 1/a. `score_kind` stays `heuristic` because the speech-weighted mean is still not a probability. Platt scaling is monotonic, so it cannot fix windows where AI and human logits overlap; the 2026-10-22 dev data overlaps under white noise at 30, 20 and 10 dB SNR.

# Rollback and release evidence

Turn off `CURRENT_EVIDENCE_ENABLED` and `QUIET_ELIGIBILITY_ENABLED`, and set `SCORING_WIRE_VERSION=call-evidence-v1`. Keep the iOS presentation contradiction fix and freshness handling. Rollback changes no checkpoint or thresholds. Tests verify default flags and legacy fixture decoding; exercise the version-targeted cohort with actual older/newer devices before a staged deployment.

`tools/build_contract_fixtures.py` regenerates actual packets in `evidence-v2-fixtures.json` for Python/Swift replay: no evidence, fresh warning, pending, timeout, failure, recovery and stale evidence. `test_current_evidence.py` checks bounded history, overlap accounting, silence, generation handling, gate controls, and integrity fail-closed behavior. These are synthetic/mocked integration checks, not phone-call or held-out accuracy results.

Local model startup verifies the pinned official architecture revision, detector config and checkpoint SHA-256 before `torch.load(weights_only=True)`, then runs a warmup and checks finite output. No online architecture lookup occurs. A replacement checkpoint/config needs an explicitly reviewed integrity manifest and separate release. Remote service health is checked, but older service health responses lacking integrity metadata are labeled `integrity_verified: false`; they are not silently described as hash-verified local bundles.

No real calls, cloud deployment/load tests, independent held-out recordings, calibration or retraining are performed by these tests. Such work depends on consented data, training provenance and deployment access. The generated disclosure asset uses macOS Samantha and exact text “This call is being recorded.”; its format/hash test does not establish intelligibility over the deployed phone route.
