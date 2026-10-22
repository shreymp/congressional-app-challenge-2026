# Jev scam-call post-training experiment

For the later recorded-call fine-tuning passes (V3–V5), public-audio probes, hard-negative regressions, and explicit deployment decision, read [the October 20 evaluation](../../docs/testing/2026-10-20-transcript/REPORT.md) and [research methods](../../docs/testing/2026-10-20-transcript/RESEARCH.md). Results below describe the earlier synthetic-data runs, not real-world validation.

This run starts from the public 151M-parameter GLiClass/ModernBERT Jev checkpoint and fine-tunes it for one proposition: **“The caller is attempting to scam or defraud the other person.”** It was trained locally on the Mac GPU. The app's existing ten caller-behavior questions are a different task and were not given fabricated labels.

## Data

| Dataset | Local use | Published source |
| --- | --- | --- |
| [Phone Scam Dataset](https://huggingface.co/datasets/menaattia/phone-scam-dataset) | 1,200 of 3,200 train calls; 800 held-out test calls | Binary scam/legitimate. License not stated in the dataset card. |
| [BothBosu scam-dialogue](https://huggingface.co/datasets/BothBosu/scam-dialogue) | 1,200 of 1,278 deduplicated train calls; 320 held-out test calls | Synthetic, Apache 2.0. |
| [Phone Scam Detection Synthetic](https://huggingface.co/datasets/shakeleoatmeal/phone-scam-detection-synthetic) | 1,200 of 1,259 train calls; 361 validation calls; 180 held-out test calls | Synthetic, MIT. |
| [ICFD-31k](https://huggingface.co/datasets/rishia2220/icfd-31k) | Downloaded and checksum verified; 500 clear-normal and 500 clear-fraud calls for cross-source stress testing only | Synthetic English/Hinglish, defensive-use terms. |
| [Kaggle Scam and Non-Scam Calls](https://www.kaggle.com/datasets/teeconnie/scam-and-non-scam-call-conversation-dataset) | 400 scam and 400 benign short texts, reserved for external evaluation | Based partly on reported cases and partly generated; CC BY-NC-ND 4.0. |

The upstream Jev repository's 500-example `data/val.jsonl` is saved locally as `data/raw/upstream_jev/val.jsonl` for the original-task retention check.

The [Indian Cyber Scam Hinglish dataset](https://huggingface.co/datasets/ysangam/Indian_Cyber_Scam_PhoneCall_Hinglish_Dataset) was also downloaded. Its downloaded CSV lacks a reliable channel column for selecting calls, so it was excluded. Other candidates and their limitations are listed in [JEV_POSTTRAIN_DATASETS.md](../../JEV_POSTTRAIN_DATASETS.md).

The [BothBosu multi-agent](https://huggingface.co/datasets/BothBosu/multi-agent-scam-conversation) and [single-agent](https://huggingface.co/datasets/BothBosu/single-agent-scam-conversations) variants were downloaded after the run and were not added to this checkpoint because they belong to the same synthetic source family. Their files are available locally for later experiments.

The downloaded file paths, sizes, and SHA-256 hashes are recorded in `download_manifest.json`.

`prepare.py` preserves published train/test splits, removes exact cross-split transcript duplicates, and samples a balanced 3,600-call training set. A character-ngram audit found no exact train/holdout overlap, but 16 of 1,300 test calls had cosine similarity at least 0.8 to a training call, all from BothBosu. All performance figures below are on **synthetic or synthetic-style** data; no real-world call quality is established.

## Method and results

The first full-model run used two epochs, batch size 4 with four-step gradient accumulation, AdamW at 2e-5, cross-entropy plus Brier loss, and the latest 300 transcript tokens within Jev's 512-token input budget. Epoch 2 was selected by validation NLL. A binary temperature of 2.278 was fitted on the 361 validation calls. The score is calibrated only for this synthetic validation distribution.

A second local pass started from the first checkpoint and used 3,599 caller-only versions of the same training calls for one epoch at 1e-5. One call lacking a caller role tag was excluded. This raised caller-only validation accuracy from 90.0% to 98.3%, but reduced full-dialogue validation accuracy from 97.5% to 95.6%. A separate temperature of 3.012 was fitted on the original full-dialogue validation set. It is saved as a separate short-call variant.

| Evaluation | Original Jev | Call v1 | Caller-only v2 |
| --- | ---: | ---: | ---: |
| Held-out calls from three training-source families, n=1,300 | 46.5% | **99.5%** | 98.5% |
| Held-out calls, binary Brier score | 0.2591 | **0.0042** | 0.0128 |
| ICFD cross-source synthetic stress test, n=1,000 | 44.7% | 87.8% | **88.1%** |
| Kaggle short-call external test, n=800 | 40.5% | 72.5% | **79.6%** |
| Original Jev decision validation, n=500 | 56.4% | **69.0%** | 67.6% |

The ICFD test uses clear-normal calls from ICFD's train split and clear-fraud calls from its test split because ICFD's official test split lacks normal calls. No ICFD data was used to train either checkpoint. That result is a cross-source stress test, not the official ICFD benchmark. The held-out three-family test was inspected after a 600-example pilot; treat the final scores as exploratory rather than a fresh blind test. Kaggle entries had numeric indices stripped from scam texts before scoring. None of its 800 entries reached 0.8 character-ngram cosine similarity to a training dialogue. Kaggle scam recall rose from **53.8%** with v1 to **69.3%** with v2, but remains weak; 10-bin calibration error fell from **0.217** to **0.144**. ICFD clear-normal specificity dropped from **93.2%** with v1 to **80.2%** with v2. The second pass was motivated by inspecting the Kaggle result, so the Kaggle comparison is an exploratory development result.

The model's prompts ask for a whole-call scam verdict, while the iOS app asks ten individual behavior questions. A qualitative probe found that **both new checkpoints marked all ten behaviors near 1.0** on a bank verification-code scam, even though that transcript contains no request for money or an unusual payment method. On a dentist rescheduling call, v1 still scored verification-code request at 0.745 and urgency at 0.989. These scores are uncalibrated for individual behaviors. The fine-tuned model also assigns almost no mass to “insufficient evidence” on the training-style scam prompt. Keep the shipped on-device scorer unchanged until there is a separately labeled, real-call, prefix-level ten-signal test and native parity check.

No accounts were created and no paid services were used. The local checkpoint includes data from a source with no stated license, so its reuse or distribution should be reviewed before publication.

## Download the post-trained models after cloning

```sh
python3 ios/scripts/setup_posttrained_jev.py
```

This downloads the exact V1 and caller-only V2 ONNX exports, tokenizers, and calibration files from the repository's `jev-call-models-v1-v2` GitHub release into `ios/ScamTranscript/Resources/JevCallV1` and `JevCallV2`. All six files are SHA-256 verified using `model_downloads.json`. Existing verified files are reused. Allow about 1.22 GB of downloads and disk space. Python 3.9 or newer is sufficient; no extra packages are needed.

`scripts/download_jev_model.py` downloads the upstream starting model, separately from these locally post-trained checkpoints.

## Artifacts and reproduction

- Trainable checkpoint: `runs/call-v1/model.safetensors`
- ONNX export: `runs/call-v1/model.onnx`
- Caller-only variant: `runs/call-v2-caller/model.safetensors` and `runs/call-v2-caller/model.onnx`
- Run details: `runs/call-v1/train_manifest.json`, `evaluation.json`, `ood-evaluation.json`, `retention.json`, and `export_manifest.json`
- Ten-signal qualitative probe: `runs/signal-probe.json`
- Data and binary artifacts are ignored by Git. The ONNX export passed `onnx.checker` and matched PyTorch logits within 0.000014 on two validation prompts.

From the repository root, after installing the listed dependencies in `.venv` and downloading the source files:

```sh
.venv/bin/python backend/jev-posttrain/prepare.py
.venv/bin/python backend/jev-posttrain/audit_similarity.py
.venv/bin/python backend/jev-posttrain/train.py --per-source 1200 --epochs 2
.venv/bin/python backend/jev-posttrain/train.py --model backend/jev-posttrain/runs/call-v1 --per-source 1200 --epochs 1 --caller-only --lr 1e-5 --output backend/jev-posttrain/runs/call-v2-caller
.venv/bin/python backend/jev-posttrain/evaluate.py
.venv/bin/python backend/jev-posttrain/ood.py
.venv/bin/python backend/jev-posttrain/kaggle_eval.py
.venv/bin/python backend/jev-posttrain/retention.py
.venv/bin/python backend/jev-posttrain/probe_signals.py
.venv/bin/python backend/jev-posttrain/export.py
.venv/bin/python backend/jev-posttrain/score.py 'Caller: Read me the code your bank just texted you.'
.venv/bin/python backend/jev-posttrain/score.py --checkpoint backend/jev-posttrain/runs/call-v2-caller 'Caller: Read me the code your bank just texted you.'
```

The model release belongs to this private repository. Downloading requires repository access through Git HTTPS credentials or the `GITHUB_TOKEN` (or `GH_TOKEN`) environment variable. SSH-only clones need a token for the release download. Tokens are never stored in the repository.
