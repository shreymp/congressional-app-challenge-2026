# Versioned development benchmark

The original `../README.md`, `../results/`, `../snapshots/`, `../evaluate.py` and `../report.py` remain frozen. `frozen_baseline_manifest.json` records 110 preserved files. Every run validates them before and after execution and refuses to overwrite an existing output directory.

From the repository root:

```sh
.venv/bin/python 'model teseting/benchmark/run.py' \
  --ai-audio '/path/to/ElevenLabs.mp3' \
  --human-audio 'model teseting/audio/human_controls/librispeech_test_clean_1320_40s.wav' 'model teseting/audio/human_controls/librispeech_test_clean_6930_40s.wav' \
  --model-dir 'model teseting/weights' --device mps \
  --output 'model teseting/benchmark/runs/UNIQUE-RUN-NAME'
```

`--device cpu` is supported. `--baseline-dir`, `--current-dir`, `--candidate-dir`, `--architecture-dir`, `--model-source-dir`, `--model-dir`, `--config`, and all audio paths are explicit. Audio decoding records its actual sample rate and resamples by its measured integer rate. The supplied checkpoint is pinned by SHA-256 in the versioned config; a deliberate checkpoint experiment needs a separate config. No thresholds are changed or calibrated by this runner. Undeclared threshold environment overrides are rejected. Inference uses the official architecture configuration locally and never downloads a replacement.

Each successful run includes a dependency lock, runtime/device/seed metadata, checkpoint/config/architecture/source hashes, a saved runner, a frozen candidate Python source copy, exact PCM/input hashes and submitted source intervals, per-window raw logits, measured completion times, call-end cancellation, per-frame quality telemetry, rejected attempt reasons, a factorial report and CSVs. The original 18 regression names are preserved. Missing named cases remain explicit in the manifest and reproduction checks.

There are three real-inference selection paths: old speech-only input, updated contiguous input, and opt-in adaptive eligibility. Each selection's **same completed outputs** are replayed through old and updated aggregators, giving the full 2×2 attribution experiment, plus bounded current mean and time-decayed candidates. Candidate 1/2-second overlap on three transition/clean cases invokes real inference and retains exact intervals. Only newly added audio contributes to the candidate engine; these are development experiments, not a deployment cadence recommendation.

The runner extends both human controls with the same degradations applied to AI, and includes an actual 128 kb/s 44.1 kHz MP3 encoding when local ffmpeg is available. It adds deterministic silence, white/pink noise, DTMF, and synthesized music at two RMS levels. Synthetic music is not a substitute for consented hold music, TV, or background conversation. Every derivative remains grouped with its original recording. The original AI audio already contains its original MP3 encoding; an MP3 human control narrows that confound but does not create a matched microphone/speaker pair.

The report separates current classification, qualified warning presentation, whole-call/reference behavior, transient warning persistence, first detection, every labeled switch/recovery (including unreached outcomes), incorrect-Human duration, abstention, quality rejection, submission/completion/publication, and analysis coverage. `publication_at` is a simulated same-process replay event; it is not an app receipt or physical display measurement. Model completion times are measured on this device; connection, disclosure, network and device timing are not simulated as zero-cost live evidence.

`frozen_reproduction.json` checks all 18 cases against the preserved exact input hashes/intervals, completion/cancellation outcomes, and raw logits with absolute tolerance 0.01. New measured inference timestamps may differ. The qualified display policy intentionally changes Human+warning presentation and is separate from model classification. The baseline files are never regenerated.

Run logic checks separately:

```sh
.venv/bin/python -m unittest discover -s 'model teseting/benchmark/tests' -v
```

Independent held-out evaluation, actual live-call results, consented same-speaker pairs, training-data overlap, calibration selection, deployment concurrency and operational release budgets remain separate required work. A reused-case improvement is not evidence of population accuracy. In particular, this run can reveal that a candidate improves transitions while adding human false warnings; it never silently selects that candidate for production.
