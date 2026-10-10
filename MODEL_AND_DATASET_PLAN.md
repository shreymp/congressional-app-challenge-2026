# Scam Guardian: On-Device Model and Dataset Plan

This plan separates models that belong on the phone from training datasets that
belong in the development environment. No raw call audio should be retained
after on-device inference.

## Recommended first deployment stack

| Job | Recommended open-weight starting point | Why it fits the prototype | Deployment target |
| --- | --- | --- | --- |
| Voice-deepfake signal | AASIST-L | The official implementation reports 85,306 parameters. It consumes mono 16 kHz waveforms directly and is vastly more practical than SSL front ends for an iPhone 11 / Android 11 first pass. | Export a tested fixed-window model to Core ML and ONNX Runtime Mobile / TFLite. |
| Speaker-consistency signal | SpeechBrain ECAPA-TDNN VoxCeleb | Apache-2.0 pretrained speaker embeddings. Use cosine similarity only after explicit contact enrollment. | Export the embedding network to ONNX/Core ML; store enrolled embeddings, not recordings. |
| On-device transcription | Whisper `tiny.en` or `base.en` through whisper.cpp | whisper.cpp has maintained Android and iOS integrations and supports fully offline inference. Begin with `tiny.en`; only move to `base.en` after measured real-time tests. | Native C/C++ binding; run only after VAD reports speech. |
| Kev transcript signals | Fine-tuned Kev/Verdict-style decision model | A rolling transcript window becomes one state, then Kev answers ten concrete behavior questions in one pass: money, credentials, verification code, personal information, urgency, pressure, fear/threat, secrecy, unusual payment, and impersonation. This is better than a generic scam classifier because each signal is easier to learn, explain, test, and calibrate. | ONNX Runtime locally first; later convert or replace with a tested mobile export. |

## Downloaded training suite

| Dataset | Role | Included content | Important limitation |
| --- | --- | --- | --- |
| ASVspoof 2019 LA | Fine-tune deepfake detector | Labeled bona-fide and synthetic/converted speech plus official partitions. | It is not telephone audio; add codec, packet-loss, noise, and reverberation augmentation. Do not use the evaluation split to train. |
| LibriSpeech train-clean-100 | Speech / speaker adaptation | 100 hours of labeled 16 kHz English audio from many speakers. | Audiobook speech is not conversational calls; use it for pipeline adaptation, not final call-domain claims. |
| Kev transcript chunks | Fine-tune transcript behavior signals | Rolling call chunks labeled with ten yes/no behavior labels. Synthetic calls can provide volume, but hard legitimate negatives and human spot checks are required. | Do not train only on scams versus small talk. Include banks, doctors, family, IT desks, and other legitimate calls that mention sensitive topics without scam behavior. |

## Hold-out data, not initial training downloads

ASVspoof 2021 DF is 34.5 GB. Keep it isolated as a later robustness evaluation
set. Cross-dataset results matter more than an in-domain score: the deployed
model must be evaluated after telephone-codec and noisy-call transformations.

## Required experiments before app integration

1. Convert every input to mono 16 kHz PCM and score a 2–4 second rolling window.
2. Measure p50/p95 latency, peak RSS, thermal state, and battery impact on an iPhone 11 and Android 11 device.
3. Calibrate the deepfake score on held-out, telephone-degraded samples; never map an uncalibrated score directly to a warning.
4. Treat each Kev output as a behavior signal, not a final scam verdict.
5. Before fine-tuning Kev, run a contrast check: an obvious code-request transcript should separate clearly from a benign dentist-rescheduling transcript. The current zero-shot adapter does not pass this quality bar, so do not claim detection accuracy from it.
6. Add speaker labels to transcript windows. Most labels are about what the caller does, and unlabeled user statements can create false positives.
7. Keep text windows near the model's tested context length, use overlap, and include messy speech-to-text output during training and evaluation.
8. Calibrate Kev per signal on held-out data and report Brier score plus expected calibration error before quoting probabilities.
