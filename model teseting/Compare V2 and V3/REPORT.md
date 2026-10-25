# Compare V2 and V3 — October 23, 2026

Paired local inference on three previously used ElevenLabs recordings (Shrey, Keshav, Azim), two 40-second LibriSpeech human controls, and the previous deterministic distortions and diagnostics.

Scored 677 complete windows across 65 cases, with 467 unique normalized inputs per model. Primary speech metrics use 474 windows (48 original-bandwidth windows). Repeated inputs were scored once per model and mapped back to every occurrence.

| Speech subset / operating point | Model | Accuracy | Balanced accuracy | AI detected | Human false positives | AUC | EER |
|---|---|---:|---:|---:|---:|---:|---:|
| original_only / threshold_eer | V2 | 70.8% | 65.0% | 100.0% | 70.0% | 1.0000 | 0.0% |
| original_only / threshold_eer | V3 | 93.8% | 94.6% | 89.3% | 0.0% | 1.0000 | 0.0% |
| original_only / threshold_1pct_fpr | V2 | 89.6% | 87.5% | 100.0% | 25.0% | 1.0000 | 0.0% |
| original_only / threshold_1pct_fpr | V3 | 64.6% | 69.6% | 39.3% | 0.0% | 1.0000 | 0.0% |
| all_speech_conditions / threshold_eer | V2 | 76.2% | 71.2% | 99.6% | 57.1% | 0.9608 | 11.8% |
| all_speech_conditions / threshold_eer | V3 | 86.9% | 88.5% | 79.1% | 2.0% | 0.9837 | 7.2% |
| all_speech_conditions / threshold_1pct_fpr | V2 | 88.8% | 88.1% | 92.1% | 15.8% | 0.9608 | 11.8% |
| all_speech_conditions / threshold_1pct_fpr | V3 | 55.1% | 61.7% | 23.4% | 0.0% | 0.9837 | 7.2% |

The `1pct_fpr` name describes the supplied training-validation operating point; it does not guarantee 1% false positives on these recordings. AUC and EER describe ranking on this reused set; EER is diagnostic only, with no resulting threshold adopted.

## By audio condition (supplied EER thresholds)

| Condition | AI / human windows | V2 balanced accuracy | V3 balanced accuracy | V2 human FP | V3 human FP | V2 AI detection | V3 AI detection |
|---|---:|---:|---:|---:|---:|---:|---:|
| original_only | 28 / 20 | 65.0% | 94.6% | 70.0% | 0.0% | 100.0% | 89.3% |
| 8khz_bandwidth_only | 28 / 20 | 82.5% | 96.4% | 35.0% | 0.0% | 100.0% | 92.9% |
| g711_mulaw | 28 / 20 | 77.5% | 92.9% | 45.0% | 0.0% | 100.0% | 85.7% |
| low_volume_minus20dB | 28 / 20 | 62.5% | 92.9% | 75.0% | 0.0% | 100.0% | 85.7% |
| mild_clipping | 28 / 20 | 70.0% | 92.9% | 60.0% | 0.0% | 100.0% | 85.7% |
| pause_10s_after_16s | 27 / 18 | 66.7% | 94.4% | 66.7% | 0.0% | 100.0% | 88.9% |
| pause_2s_after_16s | 27 / 18 | 66.7% | 94.4% | 66.7% | 0.0% | 100.0% | 88.9% |
| white_noise_10dB_SNR | 28 / 20 | 85.7% | 61.4% | 25.0% | 20.0% | 96.4% | 42.9% |
| white_noise_20dB_SNR | 28 / 20 | 72.5% | 78.6% | 55.0% | 0.0% | 100.0% | 57.1% |
| white_noise_30dB_SNR | 28 / 20 | 62.5% | 87.5% | 75.0% | 0.0% | 100.0% | 75.0% |

## Original recordings

| Recording | Model | AI / human windows | Median raw logit | Correct at EER threshold |
|---|---|---:|---:|---:|
| ai_source | V2 | 9 / 0 | 25.947 | 9 / 9 |
| ai_source | V3 | 9 / 0 | 5.225 | 7 / 9 |
| librispeech_test_clean_1320_40s | V2 | 0 / 10 | 15.409 | 2 / 10 |
| librispeech_test_clean_1320_40s | V3 | 0 / 10 | -4.599 | 10 / 10 |
| librispeech_test_clean_6930_40s | V2 | 0 / 10 | 12.544 | 4 / 10 |
| librispeech_test_clean_6930_40s | V3 | 0 / 10 | -6.409 | 10 / 10 |
| 2026-10-23T02_47_03_keshav_ivc_sp100_s50_sb75_v4 | V2 | 10 / 0 | 25.074 | 10 / 10 |
| 2026-10-23T02_47_03_keshav_ivc_sp100_s50_sb75_v4 | V3 | 10 / 0 | 4.911 | 9 / 10 |
| 2026-10-23T02_47_47_azim_ivc_sp100_s50_sb75_v4 | V2 | 9 / 0 | 26.912 | 9 / 9 |
| 2026-10-23T02_47_47_azim_ivc_sp100_s50_sb75_v4 | V3 | 9 / 0 | 5.546 | 9 / 9 |

## Interpretation and limits

The primary comparison changes both model weights and their supplied validation thresholds. `threshold_crossover.csv` also evaluates both models under both threshold sets to expose this interaction. Comparing the old and new training reports directly would mix different validation populations and conditions.

- Only three ElevenLabs source recordings and two human speakers; derivatives/windows are correlated.
- LibriSpeech is in-corpus for V3; supplied config says speakers 1320 and 6930 excluded, not independently audited.
- ElevenLabs training overlap unknown; these are reused development recordings.
- Noise/music/DTMF are synthetic controls; no real background chatter, own human recordings or live calls supplied.
- Only complete four-second windows are scored; tails, mixed windows and inserted silence excluded from speech accuracy.
- Scores are uncalibrated. A lower AI score by itself is not proof of better accuracy; both AI detection and human false positives are reported.
- Fixed-window transition diagnostics, mixed-boundary windows, inserted silence, and synthetic non-speech probes are retained separately and are not independent speech examples. No call-state or live-call performance claim is made.
- No population confidence interval or significance claim is justified by five source recordings. More real human recordings from outside the training corpora are needed to assess generalization.

## Reproduction

Device: mps; float32; PyTorch 2.14.1. Single-window GPU timings include synchronization and host transfer; they exclude warm-up and are not live-call latency.

Inputs, checkpoint/config checksums, architecture, source snapshots, normalized windows and exact window hashes are saved under `inputs/` and `sources/`. Per-window logits, summaries, threshold crossover and separate non-speech probes are under `results/`. Dependencies and progress logs are under `logs/`. Frozen earlier benchmark files were verified before and after inference.

