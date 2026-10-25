# Development interpretation

This report contains reused and transformed development sources. No independent accuracy, calibrated probability, live-call latency, or release readiness is established.

## Coverage and provenance

Cases: 45. Actual model inferences: 2852. Device: mps.
Frozen reproduction: True.

All derived clips retain source groups. The speech recordings comprise one AI source and two human source recordings; transforms and repeated prefixes are not additional independent calls. Synthetic controls have their own explicit groups.

## Current evidence and eligibility

| Case | Experiment | Completed | Incorrect Human s | False AI s | False warning s | Switch target delays s | Final |
|---|---|---:|---:|---:|---:|---|---|
| original | current__current | 9 | 0.00 | 0.00 | 0.00 | ai: 8.02 | ai |
| original | current__candidate_mean | 9 | 0.00 | 0.00 | 0.00 | ai: 8.02 | ai |
| original | current__candidate_decay | 9 | 0.00 | 0.00 | 0.00 | ai: 8.02 | ai |
| original | candidate_quiet__candidate_mean | 9 | 0.00 | 0.00 | 0.00 | ai: 8.02 | ai |
| original | candidate_quiet__candidate_decay | 9 | 0.00 | 0.00 | 0.00 | ai: 8.02 | ai |
| original | candidate_quiet_overlap1s__candidate_mean | 35 | 0.00 | 0.00 | 0.00 | ai: 5.02 | ai |
| original | candidate_quiet_overlap2s__candidate_mean | 18 | 0.00 | 0.00 | 0.00 | ai: 6.02 | ai |
| low_volume_minus20dB | current__current | 0 | 0.00 | 0.00 | 0.00 | ai: unreached | uncertain |
| low_volume_minus20dB | current__candidate_mean | 0 | 0.00 | 0.00 | 0.00 | ai: unreached | uncertain |
| low_volume_minus20dB | current__candidate_decay | 0 | 0.00 | 0.00 | 0.00 | ai: unreached | uncertain |
| low_volume_minus20dB | candidate_quiet__candidate_mean | 9 | 0.00 | 0.00 | 0.00 | ai: 8.02 | ai |
| low_volume_minus20dB | candidate_quiet__candidate_decay | 9 | 0.00 | 0.00 | 0.00 | ai: 8.02 | ai |
| white_noise_10dB_SNR | current__current | 9 | 0.00 | 0.00 | 0.00 | ai: unreached | uncertain |
| white_noise_10dB_SNR | current__candidate_mean | 9 | 0.00 | 0.00 | 0.00 | ai: 20.02 | uncertain |
| white_noise_10dB_SNR | current__candidate_decay | 9 | 0.00 | 0.00 | 0.00 | ai: 16.02 | uncertain |
| white_noise_10dB_SNR | candidate_quiet__candidate_mean | 9 | 0.00 | 0.00 | 0.00 | ai: 23.18 | ai |
| white_noise_10dB_SNR | candidate_quiet__candidate_decay | 9 | 0.00 | 0.00 | 0.00 | ai: 21.02 | ai |
| librispeech_test_clean_1320_40s | current__current | 9 | 0.00 | 0.00 | 0.00 | human: unreached | uncertain |
| librispeech_test_clean_1320_40s | current__candidate_mean | 9 | 0.00 | 5.76 | 4.00 | human: 24.34 | uncertain |
| librispeech_test_clean_1320_40s | current__candidate_decay | 9 | 0.00 | 6.16 | 4.00 | human: 24.22 | uncertain |
| librispeech_test_clean_1320_40s | candidate_quiet__candidate_mean | 9 | 0.00 | 5.86 | 4.00 | human: 24.40 | uncertain |
| librispeech_test_clean_1320_40s | candidate_quiet__candidate_decay | 9 | 0.00 | 6.22 | 4.00 | human: 24.48 | uncertain |
| librispeech_test_clean_6930_40s | current__current | 9 | 0.00 | 0.00 | 0.00 | human: 8.02 | uncertain |
| librispeech_test_clean_6930_40s | current__candidate_mean | 9 | 0.00 | 0.78 | 0.00 | human: 8.02 | human |
| librispeech_test_clean_6930_40s | current__candidate_decay | 9 | 0.00 | 1.04 | 0.00 | human: 8.02 | human |
| librispeech_test_clean_6930_40s | candidate_quiet__candidate_mean | 9 | 0.00 | 0.86 | 0.00 | human: 8.02 | human |
| librispeech_test_clean_6930_40s | candidate_quiet__candidate_decay | 9 | 0.00 | 1.06 | 0.00 | human: 8.02 | human |
| diagnostic_human_prefix120_then_ai | current__current | 39 | 12.02 | 0.00 | 0.00 | human: 8.02, ai: unreached | recent_warning |
| diagnostic_human_prefix120_then_ai | current__candidate_mean | 39 | 9.80 | 0.00 | 0.00 | human: 8.02, ai: 12.02 | ai |
| diagnostic_human_prefix120_then_ai | current__candidate_decay | 39 | 9.40 | 0.00 | 0.00 | human: 8.02, ai: 12.02 | ai |
| diagnostic_human_prefix120_then_ai | candidate_quiet__candidate_mean | 39 | 10.10 | 0.00 | 0.00 | human: 8.02, ai: 12.02 | ai |
| diagnostic_human_prefix120_then_ai | candidate_quiet__candidate_decay | 39 | 9.58 | 0.00 | 0.00 | human: 8.02, ai: 12.02 | ai |
| diagnostic_human_prefix120_then_ai | candidate_quiet_overlap1s__candidate_mean | 155 | 6.32 | 0.00 | 0.00 | human: 18.26, ai: 9.26 | ai |
| diagnostic_human_prefix120_then_ai | candidate_quiet_overlap2s__candidate_mean | 78 | 7.22 | 0.00 | 0.00 | human: 17.76, ai: 10.02 | ai |
| diagnostic_ai_then_human6930 | current__current | 19 | 0.00 | 40.00 | 13.67 | ai: 8.02, human: unreached | ai |
| diagnostic_ai_then_human6930 | current__candidate_mean | 19 | 0.00 | 14.21 | 8.41 | ai: 8.02, human: 37.21 | human |
| diagnostic_ai_then_human6930 | current__candidate_decay | 19 | 0.00 | 13.69 | 8.41 | ai: 8.02, human: 37.21 | human |
| diagnostic_ai_then_human6930 | candidate_quiet__candidate_mean | 19 | 0.00 | 15.45 | 9.55 | ai: 8.02, human: 36.07 | human |
| diagnostic_ai_then_human6930 | candidate_quiet__candidate_decay | 19 | 0.00 | 14.23 | 9.55 | ai: 8.02, human: 35.91 | human |
| diagnostic_ai_then_human6930 | candidate_quiet_overlap1s__candidate_mean | 75 | 0.00 | 15.67 | 11.23 | ai: 5.02, human: 18.99 | human |
| diagnostic_ai_then_human6930 | candidate_quiet_overlap2s__candidate_mean | 38 | 0.00 | 14.51 | 11.21 | ai: 6.02, human: 18.87 | human |

## Non-speech controls

| Case | Selection | Submitted/completed | Mean speech estimate weight | Candidate mean confident seconds |
|---|---|---:|---:|---:|
| control_silence | baseline | 0/0 | 0.000 | 0.00 |
| control_silence | current | 0/0 | 0.000 | 0.00 |
| control_silence | candidate_quiet | 0/0 | 0.000 | 0.00 |
| control_white_noise_rms0.003 | baseline | 0/0 | 0.000 | 0.00 |
| control_white_noise_rms0.003 | current | 0/0 | 0.000 | 0.00 |
| control_white_noise_rms0.003 | candidate_quiet | 0/0 | 0.000 | 0.00 |
| control_white_noise_rms0.03 | baseline | 18/17 | 1.000 | 15.98 |
| control_white_noise_rms0.03 | current | 5/4 | 1.000 | 11.98 |
| control_white_noise_rms0.03 | candidate_quiet | 0/0 | 0.000 | 0.00 |
| control_pink_noise_rms0.003 | baseline | 0/0 | 0.000 | 0.00 |
| control_pink_noise_rms0.003 | current | 0/0 | 0.000 | 0.00 |
| control_pink_noise_rms0.003 | candidate_quiet | 0/0 | 0.000 | 0.00 |
| control_pink_noise_rms0.03 | baseline | 18/17 | 1.000 | 0.00 |
| control_pink_noise_rms0.03 | current | 5/4 | 1.000 | 0.00 |
| control_pink_noise_rms0.03 | candidate_quiet | 0/0 | 0.000 | 0.00 |
| control_dtmf_rms0.003 | baseline | 0/0 | 0.000 | 0.00 |
| control_dtmf_rms0.003 | current | 0/0 | 0.000 | 0.00 |
| control_dtmf_rms0.003 | candidate_quiet | 5/4 | 0.500 | 11.98 |
| control_dtmf_rms0.03 | baseline | 15/14 | 1.000 | 12.98 |
| control_dtmf_rms0.03 | current | 5/4 | 0.500 | 11.98 |
| control_dtmf_rms0.03 | candidate_quiet | 5/4 | 0.500 | 11.98 |
| control_synthetic_music_rms0.003 | baseline | 0/0 | 0.000 | 0.00 |
| control_synthetic_music_rms0.003 | current | 0/0 | 0.000 | 0.00 |
| control_synthetic_music_rms0.003 | candidate_quiet | 5/4 | 0.656 | 11.98 |
| control_synthetic_music_rms0.03 | baseline | 17/16 | 1.000 | 14.98 |
| control_synthetic_music_rms0.03 | current | 5/4 | 0.907 | 11.98 |
| control_synthetic_music_rms0.03 | candidate_quiet | 5/4 | 0.656 | 11.98 |

## Symmetric degradation logits

Medians describe correlated windows within a source/condition. They are not speaker-level uncertainty estimates. No threshold is selected from this table.

| Source/condition | Fixed contiguous median logit | Adaptive median logit |
|---|---:|---:|
| original | 25.947 | 25.947 |
| 8khz_bandwidth_only | 26.667 | 26.667 |
| g711_mulaw | 21.773 | 21.773 |
| low_volume_minus20dB | unscored | 25.757 |
| mild_clipping | 25.549 | 25.549 |
| white_noise_30dB_SNR | 21.918 | 21.918 |
| white_noise_20dB_SNR | 19.422 | 19.422 |
| white_noise_10dB_SNR | 15.514 | 15.514 |
| librispeech_test_clean_1320_40s | 15.678 | 15.678 |
| librispeech_test_clean_6930_40s | 12.977 | 12.977 |
| librispeech_test_clean_1320_40s__8khz_bandwidth_only | 13.951 | 13.951 |
| librispeech_test_clean_1320_40s__g711_mulaw | 13.411 | 13.411 |
| librispeech_test_clean_1320_40s__low_volume_minus20dB | unscored | 15.247 |
| librispeech_test_clean_1320_40s__mild_clipping | 14.896 | 14.896 |
| librispeech_test_clean_1320_40s__white_noise_30dB_SNR | 16.529 | 16.529 |
| librispeech_test_clean_1320_40s__white_noise_20dB_SNR | 13.647 | 13.647 |
| librispeech_test_clean_1320_40s__white_noise_10dB_SNR | 11.348 | 11.348 |
| librispeech_test_clean_1320_40s__pause_2s_after_16s | 15.709 | 15.709 |
| librispeech_test_clean_1320_40s__pause_10s_after_16s | 15.709 | 15.709 |
| librispeech_test_clean_6930_40s__8khz_bandwidth_only | 9.560 | 9.560 |
| librispeech_test_clean_6930_40s__g711_mulaw | 9.520 | 9.520 |
| librispeech_test_clean_6930_40s__low_volume_minus20dB | unscored | 13.282 |
| librispeech_test_clean_6930_40s__mild_clipping | 11.343 | 11.343 |
| librispeech_test_clean_6930_40s__white_noise_30dB_SNR | 13.258 | 13.258 |
| librispeech_test_clean_6930_40s__white_noise_20dB_SNR | 10.855 | 10.855 |
| librispeech_test_clean_6930_40s__white_noise_10dB_SNR | 8.046 | 8.068 |
| librispeech_test_clean_6930_40s__pause_2s_after_16s | 13.833 | 13.833 |
| librispeech_test_clean_6930_40s__pause_10s_after_16s | 13.833 | 13.833 |

## Release interpretation

Candidates remain disabled by default. Faster recovery or restored quiet eligibility does not offset a new human false-warning regression without the predeclared independent evaluation. The current shadow warning is not exported as a default legacy alert. Original thresholds and checkpoint are unchanged.

A missing/rejected sample remains an abstention/coverage outcome; it does not disappear from the denominator. Physical call timing, disclosure delay, app receipt/display, same-speaker provenance, training overlap, real TV/chatter/music controls, and held-out calibration remain unknown. Synthetic logic, real-model replay, independent held-out data and actual live calls are separate evidence categories.
