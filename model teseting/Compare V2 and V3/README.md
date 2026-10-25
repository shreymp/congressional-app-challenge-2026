# V2 vs V3: results

**V3 improves overall discrimination and greatly reduces false AI flags on the human controls, but it misses more ElevenLabs audio. Its strict threshold is a substantial regression on these recordings.**

At each model's supplied EER threshold, across the original recordings and their phone/noise/volume/clipping/pause variants:

| Measure | V2 | V3 |
|---|---:|---:|
| Window accuracy | 76.2% | 86.9% |
| Balanced accuracy | 71.2% | 88.5% |
| Human speech falsely flagged AI | 57.1% (112/196) | 2.0% (4/196) |
| ElevenLabs AI detected | 99.6% (277/278) | 79.1% (220/278) |
| AUC (higher is better) | 0.9608 | 0.9837 |
| Empirical EER (lower is better) | 11.8% | 7.2% |

These are **related development windows from only five source recordings**, not population accuracy estimates. In particular, V3 was trained on LibriSpeech, the corpus used for both human controls. Its config lists these two speakers as excluded, but that exclusion has not been independently audited.

## Regressions that matter

- At the supplied strict `threshold_1pct_fpr` operating point, ElevenLabs detection drops from **92.1% to 23.4%** across speech conditions. The human false-positive rate drops from 15.8% to 0%. The threshold's name does not guarantee a 1% false-positive rate here.
- On original audio, strict-threshold ElevenLabs detection falls from **28/28 to 11/28 windows**. At EER thresholds it falls from 28/28 to 25/28. V3 gets all 20 original human windows correct; V2 gets 6/20 correct at its EER threshold.
- With heavy white noise (10 dB SNR), EER-threshold balanced accuracy falls from **85.7% to 61.4%**. AI detection falls from 96.4% to 42.9%, while human false positives fall from 25% to 20%.
- V3 flags **0/45 standalone synthetic non-speech windows** at either supplied threshold. V2 flags 41/45 at EER and 35/45 at strict. These are raw model probes; the app's speech gate may reject them before inference.

V3 is promising for reducing false alarms, but this test does not support an unconditional accuracy improvement for deployment. Its strict threshold needs evaluation and calibration on separate, representative real/fake phone audio. Thresholds must be carried with their model: applying V2's thresholds to V3 misses every AI window in this set. Production model files and settings were not changed.

## What was run

- Audio: Shrey, Keshav, and Azim ElevenLabs MP3s; the two previous 40-second human controls (LibriSpeech speakers 1320 and 6930).
- 65 cases, 677 complete four-second windows, 467 unique inputs per model; exact normalized duplicates reuse their score. Primary speech comparison: 474 windows. Transitions, mixed windows, and non-speech are kept separate.
- Conditions: original, 8 kHz bandwidth, G.711 μ-law, quiet audio, clipping, white noise at 30/20/10 dB SNR, 2/10-second inserted pauses, constructed human/AI switches, silence, pink/white noise, DTMF, and synthetic music.
- Both supplied threshold sets are evaluated; no threshold was fitted to these recordings. Both checkpoints load strictly against the same pinned architecture. V3's recorded starting-checkpoint checksum exactly matches V2.
- Apple GPU inference, float32, identical PCM conversion and per-window normalization for both models. This compares model windows, not live app verdicts or timing.
- The two additional human MP3 re-encodings from the older benchmark could not be regenerated because ffmpeg is unavailable. Original ElevenLabs recordings retain their MP3 encoding. All other previous case types are present.

## Folder guide

| Item | Contents |
|---|---|
| [REPORT.md](REPORT.md) | Detailed condition tables, recording results, method and limits |
| [Comparison chart](results/comparison.png) | Main results at supplied EER thresholds |
| [results/summary.csv](results/summary.csv) | Accuracy, errors, AUC and EER by condition and threshold |
| [results/per_window.csv](results/per_window.csv) | Paired raw logits, predictions, input hashes and labels |
| [results/per_case.csv](results/per_case.csv) | Each case's median logit and EER-threshold errors |
| [results/threshold_crossover.csv](results/threshold_crossover.csv) | Both models under both supplied threshold sets |
| [results/non_speech_controls.csv](results/non_speech_controls.csv) | Raw model probes, excluded from speech accuracy |
| [results/validation.json](results/validation.json) | Integrity, metric arithmetic and independent CPU/GPU spot checks |
| inputs/ | Local copies of models/configs/audio, normalized windows, source/case/window manifests |
| sources/ | Previous inference and audio-case generator snapshots |
| logs/ | Run log, dependency versions and plotting cache |

The run is preserved. To regenerate the report and chart without model inference, run from the project root:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python 'model teseting/Compare V2 and V3/compare.py' --summarize
```

To independently recheck saved scores, run:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python 'model teseting/Compare V2 and V3/validate_results.py'
```

`compare.py` refuses to overwrite a completed inference run. Checkpoint copies are local and occupy about 1.3 GB with the saved windows; they are retained for reproducibility. Prior benchmark artifacts remain in place and their frozen checksums are verified.
