# Pinned source audit

The evaluation compares baseline `dca989c3126be4778638a002d3355a463f8789eb` with updated `ec2f4dd80de433f176b1d9f90a20ca35d60707aa`. The connected GitHub API independently returned `shrey` at exactly that updated revision during this run (client date October 22, 2026). There is no newer remote `shrey` revision to add to the requested comparison.

## Acquisition and preservation

No branch switch, reset, commit, or production edit was performed. The local checkout is `improved-ui` at `0fe9400e702abb62a2e7e9df5bd6dfd5a3cdef51`; `main` is `0f577a4`. `source_checkout_status.txt` captures this audit's status after creation of the evaluation directory: only `model teseting/` is untracked. The root agent separately recorded initial status before setup.

The recursive trees for both pinned revisions were fetched through the connected GitHub plugin, because plain git repository access lacked usable authentication. `source_connector_raw.json`, `source_trees.json`, `compare_full.json`, and `compare_after_feature.json` preserve API responses. Snapshots include all Python files under the production LiveKit directory, its requirements and docs, model implementation/configuration, and the relevant Swift production/contract sources, tests and fixtures. LiveKit files are flattened into `snapshots/{baseline,current}/`; model files are in each version's `model/`; Swift files retain repository-relative paths beneath each version.

All 87 selected snapshot files were verified against their remote Git blob IDs. Existing local files were reused only when the exact Git object hash matched. Missing or byte-different files were fetched at the full pinned revision and then verified. `source_manifest.json` maps every snapshot to its original path, revision, Git blob SHA-1, SHA-256 and optional validated local origin. Recheck offline with:

```sh
python3 "model teseting/verify_snapshots.py"
```

Both remote trees contain only `frontend/AGENTS.md`; the local checkout has the same sole instruction file. It concerns Expo frontend edits and does not apply to this evaluation. No frontend files were edited.

## Feature history and relevant subsequent changes

The graph comparison contains six commits beyond the baseline, including merges (this is a DAG comparison, not a claim of six linear first-parent commits):

| Commit | Purpose |
|---|---|
| `57d01eb592062b3e0c518241c4ab899fcba59e22` | Recording disclosure after pickup, before caller analysis |
| `c182ddaa5e07f1a582b8ee883642a01d0bf9e461` | **Cumulative feature:** bounded threshold-relative call evidence, distinct contiguous windows, recent warning, 15-second Swift initial assessment |
| `02490460448c666ffcab17e49e420a97998cbf41` | More deadline/coordinator/UI regression tests |
| `e3fac076f708f233817b3c244a0aa552b83a8276` | iOS simulator isolation from unsupported CallKit resets |
| `af18bcb81e7b0f0cb1a7420dfd4c5e7f6c0470d6` | Merge recording-disclosure PR #20 |
| `ec2f4dd80de433f176b1d9f90a20ca35d60707aa` | Merge main into shrey |

The post-feature comparison does **not** change `audio_window.py`, `risk.py`, `scoring.py`, `detector_adapter.py`, `inference.py` or `detector_config.json`. It does merge recording-notice gating into the agent and changes simulator/deadline-related iOS code/tests and documentation. Real non-probe production calls start audio analysis only after the recording disclosure succeeds. The replay evaluates caller audio from its chosen analysis origin; it does not measure disclosure duration or answer-to-first-audio delay.

## What changed

This is more than an aggregation-only production change:

- **Identical:** `inference.py` (Git blob `6a72a7469627d6242e8a004145886466457f3a14`), `detector_config.json` (`6aa985a04b0aae7b6af2683e59112f7f2a861451`), `detector_adapter.py` (`6224e97252f73480e511c6905d00d0591dccc790`). Same architecture, per-window normalization, adapter input tiling/cropping, raw-logit path, and model thresholds. The evaluation uses the same externally supplied checkpoint for both; no checkpoint is embedded in either source snapshot.
- **Model:** facebook/wav2vec2-xls-r-300m configuration, 12 retained transformer layers, learned layer weighting, projection, attentive mean/std pool, scalar classification head; 16 kHz mono and 4-second model input.
- **Unchanged detector thresholds:** elevated/EER `0.9999904632568359`; high/1%-FPR label in metadata `0.9999998807907104`. These names describe configuration provenance; they are not empirical false-positive rates on these evaluation clips.
- **Baseline windows:** discard low-RMS frames, concatenate voiced audio, become eligible after 3 seconds of retained speech, submit a rolling window whenever more voiced samples have arrived and the one-second scheduler is eligible. Short windows are tiled to 4 seconds in the unchanged adapter.
- **Updated windows:** retain contiguous audio including pauses, require a full 4 seconds with at least 1.5 seconds above the unchanged 0.01 RMS frame gate, reject a window when more than 5% of its samples have magnitude at least 0.99, and enforce at least 4 seconds of new observed audio since the last submitted window. Weight evidence by the speech-frame fraction.
- **Baseline evidence:** raw-logit EMA (`alpha=0.4`), three qualifying updates to elevate and five to de-escalate, and reset evidence/status after 6 seconds without speech.
- **Updated evidence:** normalize raw logits relative to the unchanged two thresholds, clip normalized evidence to [-4,4], and take a speech-weighted mean over the entire call. Map with sigmoid to a 0–100 heuristic AI score. Main states use Human <=35, AI >=65, otherwise Uncertain; first classification requires two segments and subsequent changes require two qualifying updates. These are new aggregation decision rules, not changed neural-model thresholds.
- **Recent warning:** keep five recent segment evidences; require at least three recent segments, a recent weighted score >=65, and at least three individually AI-like segments. Thus recent warning and whole-call main verdict can legitimately diverge. That possibility alone does not prove a regression on actual audio.
- **Silence:** updated code clears stale rolling audio after 6 seconds without speech but retains call evidence and the verdict. The source retains the legacy `RiskEngine` for backward-compatible replay; production `AudioScoringSession` selects `CallEvidenceEngine`.
- **Scheduler:** both agents poll approximately once per second on the audio loop and allow one inference task. The next poll is set when a scheduler check runs; inference completion may delay actual submissions. The scoring session blocks submissions while pending. Generation checks changed to reject obsolete completions; inference timeout remains 10 seconds.

Exact core patches are saved as `diff_*.patch`. Empty adapter/model/config patches are evidence that these files are byte-identical.

## Prior preliminary work validation

`previous_snapshot_validation.json` checks every available matching prior snapshot under `CAC/real-audio-test` and `/tmp/cac-deepfake-eval`. All such source comparisons match the pinned remote content after ignoring only trailing newlines; some already match exactly. None of those previous controlled results are real-model accuracy evidence.

The preliminary `compare_real_audio.py` was inspected but is not taken as an authoritative production replay. It checks an integer-second modulo rather than reproducing the agent's exact `next_score` scheduling; lacks submitted-window interval/provenance tracking; leaves a pending inference at call end unreported; and reimplements a simplified Swift assessment mapping. Its staged model/config content was checked, but a fresh harness is required to capture the requested timing and contract distinctions. No production file was patched to make the evaluation pass.

Foundation contract compilation additionally required ios/Callshield/Core/CallModels.swift. It was fetched and Git-blob-verified for both refs (same blob 63fa7b7da4ead9c345a5bd794422366ad770c7af); manifest now includes 87 files. Its raw connector response is saved separately.
