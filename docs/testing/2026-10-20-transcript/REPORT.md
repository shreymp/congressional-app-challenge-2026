# Recorded-call transcript detector: October 20, 2026

The existing local Jev classifier was fine-tuned through three separate research stages and tested on public recorded-call text, public audio transcribed with the app's Vosk model, natural conversations, and difficult authored contrasts. **The work does not establish 99–100% real-world accuracy.** V5 with bounded overlapping context is the most promising development candidate in these comparisons. Its weights remain local, separate from the deployed V2 bundle.

The iOS feature work and design are documented separately: [guardians/manual blocking](../../features-2026-10-20/native.md), [blocking/reporting service](../../features-2026-10-20/backend.md), and [Phone-inspired UI](../../ui-redesign-2026-10-20/DESIGN.md). No cloud deployment, recipient message, or real telephone call was performed as part of this evaluation.

## Results, including regressions

Numbers below use a binary decision threshold of 0.5. Each cell is correct calls / tested calls. Audio, roleplay, authored material, and prior synthetic examples are deliberately separate.

| Collection | Existing V2, tail | V3, tail | V4, tail | V5, tail | V5, windows |
| --- | ---: | ---: | ---: | ---: | ---: |
| Recorded FTC/NCSU + natural Switchboard text | 19/31 | 31/31 | 30/31 | 30/31 | 31/31 |
| Benign recorded banking roleplay | 38/40 | 38/40 | 23/40 | 39/40 | 39/40 |
| Difficult authored contextual contrasts | 19/25 | 17/25 | 21/25 | 21/25 | 22/25 |
| Public audio → small Vosk → classifier | 6/6 | 6/6 | 6/6 | 6/6 | 6/6 |
| Earlier caller-only synthetic-style test | 1294/1300 | 1292/1300 | 1291/1300 | 1294/1300 | Not run |

V3 improved the selected recorded transcripts but worsened authored false alarms. V4 addressed those contrasts but incorrectly flagged 17 of 40 banking roleplays, so it was rejected. V5 started from V3, used a smaller learning rate and separate banking training calls, and selected by mean validation loss across distinct sources rather than letting hundreds of easy synthetic examples dominate. These were adaptive development passes after inspecting prior failures; none is a newly blinded benchmark.

For V5 **windows** at the app's experimental 0.75 guidance threshold:

- Recorded text: 0 missed scams out of 10, 0 false alerts out of 21 benign conversations.
- Banking roleplay: 1 false alert out of 40. There are no scam examples in this collection, so it cannot measure scam recall.
- Authored contrasts: 0 missed scams out of 12, 3 false alerts out of 13 benign examples. This remains a significant unresolved weakness.
- Audio probes: 0 missed scam clips out of 3 and 0 false alerts out of 3 bank-agent roleplay clips.

V5 tail mode misses one recorded scam and one deliberately long authored scam whose actionable request appears before a long neutral tail. Bounded window inference preserves that earlier evidence. Maximum pooling can increase false alarms and does not inherit tail-mode probability calibration; it remains an experimental score. V2's window mode actually worsened recorded-text false alarms, illustrating why this setting is not enabled globally for the old model.

Detailed raw counts, Brier/NLL/calibration errors, threshold-only selective coverage, and mode comparisons: [V3](benchmark.json), [V4](benchmark-v4.json), [V5](benchmark-v5.json). Selecting confident predictions while omitting abstentions is not overall accuracy.

## What was actually recorded

- **FTC/NCSU:** 1,432 metadata rows were inspected. Three explicit English impersonation/threat categories were selected and duplicates removed; 1,198 ambiguous, excluded, non-English, short, or duplicate entries were omitted. Enforcement provenance plus content filtering yields silver labels, not independently adjudicated fraud truth.
- **Switchboard:** natural recorded two-person conversations. The model sees one speaker's words. Casual-conversation context supplies benign labels; this is not a dedicated fraud annotation and does not cover every legitimate business call.
- **Harper Valley Bank:** recorded human banking roleplay. The forty external probes and three audio tracks were excluded from training. For V5, a separate 160 calls were used for training and 32 for validation, with no call-ID or normalized exact-text overlap with the forty probes. Speakers and scenarios may overlap, and earlier probe failures motivated this added source.
- **YouTube:** three actual FTC scam-example recordings: [Amazon charge](https://www.youtube.com/watch?v=HlTpousFPsM), [auto warranty](https://www.youtube.com/watch?v=8sT121uUFOo), and [Social Security threat](https://www.youtube.com/watch?v=IQyu_yFqWGA). These are brief robocalls, not sustained live human scam conversations. Related scripts may occur in NCSU training, so they are development audio probes, not independent fraud-call validation.

All six recordings were converted to 16 kHz mono PCM and transcribed with `vosk-model-small-en-us-0.15`, the app's ASR model. This checks the recorded-audio-to-text path, not live telephone routing or ASR word-error rate. Natural benign audio was not substituted with synthetic speech; the benign audio here is explicitly roleplay, while natural conversation evidence is transcript-only.

Full sources, licenses, primary research, and method rationale: [RESEARCH.md](RESEARCH.md). Raw source text, audio, and model binaries are kept in ignored local research folders rather than copied into app assets or committed.

## Training and leakage checks

Recorded-data splits contain 479 training examples (219 silver scam, 260 natural conversation), 31 validation examples (5/26), and 31 test examples (10/21). Character-ngram connected components group similar scam scripts and ASR variants before splitting; Switchboard speakers are assigned globally to one split.

[The data audit](data-audit.json) found zero normalized exact-text, script-group, or cross-split speaker overlap. [The extended audit](extended-data-audit.json) found no normalized exact overlap with the earlier caller-only synthetic training or the later banking training texts. Similarity checks cannot prove semantic independence or correct labels. The ten positive test recordings cover **only four distinct script groups**; negative test conversations can share speakers within that split. Per-call Wilson intervals in the aggregate files are descriptive iid approximations, not valid independent-sample guarantees. Even their optimistic lower bound for 31/31 is only about 89%.

- V3: V2 base; 479 recorded examples, 479 training-only ASR-style augmentations, 600 older synthetic caller examples; two epochs, learning rate 3e-6. Validation selects epoch 2.
- V4: V3 base; same replay plus 104 authored paired training variants; one epoch at 4e-6. Twenty-four validation variants hold out entire authored scenarios. Regression on banking probes prevents promotion.
- V5: V3 base; same original training/replay/augmentation, 104 authored examples and 160 separate bank-agent roleplays; one epoch at 1e-6. Validation has 448 examples, including 32 separate banking calls and 24 authored variants. Equal-source NLL selects epoch 1. Temperature is 2.2782395705988754, fitted on validation only.

Authored variants, source-derived labels, augmentations, and natural recordings are not interchangeable counts. These are whole-call scam labels, not separately annotated labels for the app's ten individual behavior questions. The new models are not applied to those questions.

## Runtime verification and behavior changes

- Classifier control tokens supplied in a transcript are stripped before prompt construction.
- Short greetings abstain with an explicit `insufficient_evidence` response rather than manufacturing a low scam score.
- `/predict` preserves the connector contract. `/assess` additionally reports experimental score type, version, model hash, context mode and coverage; it explicitly disclaims real-call probability calibration.
- Research bundles verify the ONNX, tokenizer and temperature hashes together. V5 ONNX export passed model validation and matched reference logits within 0.000014 on the export examples.
- [V5 runtime parity](v5-runtime-parity.json): 23 inputs per mode, including six real ASR transcripts and a long context. Maximum probability difference versus PyTorch is approximately 0.000001. Real ONNX HTTP `/predict`, `/assess` and HTTP 422 abstention passed. Observed mean local CPU inference was about 32 ms tail / 39 ms windows on this sample; this is not a field-latency guarantee.
- [Streaming prefix traces](v5-prefix-trace.json) score six recordings at thirty ASR checkpoints. In the three FTC clips, the first sampled 0.75 guidance crossing occurs at 30, 30, and 20 seconds respectively. This is a concrete limit of full-clip success: an early greeting may not reveal a scam. Prefixes were not independently labeled, and checkpoints are ten seconds apart, so these traces do not establish early-call recall or actual warning latency.
- Five model-service tests, eleven transcript-pipeline tests, and the Node HTTP connector test passed. These verify mechanics with bounded test services; they do not turn a model metric into real-world validation.

Transcript score wording in the native app now uses an experimental score out of 100. The 0.75 guidance threshold is a product setting, not a verified 75% chance of fraud. Neither voice nor transcript scores create a block or automatically send a guardian message.

## Reproduction and deployment boundary

Install `backend/jev-posttrain/requirements.txt` in the local environment; audio preparation also requires ffmpeg and yt-dlp. Source input hashes are in each benchmark's `data_manifest`. Download metadata/corpus archives from their linked upstream repositories and supply those paths explicitly to `real_calls.py`; the app never downloads training data.

```sh
.venv/bin/python backend/jev-posttrain/real_calls.py --ncsu /tmp/callshield-robocall-metadata.csv --swda /tmp/callshield-swda.zip
.venv/bin/python backend/jev-posttrain/audit_real_calls.py --output docs/testing/2026-10-20-transcript/data-audit.json
.venv/bin/python backend/jev-posttrain/fetch_public_eval.py --tree /tmp/callshield-hvb-tree.json
.venv/bin/python backend/jev-posttrain/hard_negative_training.py
.venv/bin/python backend/jev-posttrain/banking_training.py --tree /tmp/callshield-hvb-tree.json
.venv/bin/python backend/jev-posttrain/finetune_real.py --epochs 2
.venv/bin/python backend/jev-posttrain/finetune_real.py --model backend/jev-posttrain/runs/call-v3-real --output backend/jev-posttrain/runs/call-v5-balanced --epochs 1 --replay 600 --lr 1e-6 --extra-train backend/jev-posttrain/data/real_calls/banking_training/train.jsonl --extra-validation backend/jev-posttrain/data/real_calls/banking_training/validation.jsonl --domain-balanced-selection
.venv/bin/python backend/jev-posttrain/audio_probes.py
.venv/bin/python backend/jev-posttrain/benchmark_real.py --candidate backend/jev-posttrain/runs/call-v5-balanced --candidate-name v5 --output docs/testing/2026-10-20-transcript/benchmark-v5.json
.venv/bin/python backend/jev-posttrain/export.py --checkpoint backend/jev-posttrain/runs/call-v5-balanced
.venv/bin/python backend/jev-posttrain/package_candidate.py --checkpoint backend/jev-posttrain/runs/call-v5-balanced --version V5 --output docs/testing/2026-10-20-transcript/v5-runtime-parity.json
.venv/bin/python backend/jev-posttrain/streaming_probe.py --checkpoint backend/jev-posttrain/runs/call-v5-balanced --version V5 --output docs/testing/2026-10-20-transcript/v5-prefix-trace.json
```

`fetch_public_eval.py` and `banking_training.py` take the upstream GitHub recursive tree JSON; source URLs and per-call checksums are retained locally. `audio_probes.py` expects the three identified FTC downloads at the explicit `/tmp/callshield-ftc-*.wav` paths documented in the script. Prepare those downloads from the linked public FTC uploads before running it; existing local research audio is retained under `data/real_calls/audio`. These are development scripts with declared local inputs, not a one-click public benchmark package.

To serve the local V5 development bundle, use [the explicit adapter command](../../../backend/Transcript-Based%20Detector/ARCHITECTURE.md#recorded-call-research-candidates). Default V2 and its released files remain available. No new weights were published, no deployment was changed, and the iOS on-device bundle remains unchanged. A production replacement needs independent source-diverse human-reviewed calls, prefix labels, validation-frozen thresholds, license review, and device/service testing. Text alone cannot verify caller identity or whether an ordinary-sounding story is true.
