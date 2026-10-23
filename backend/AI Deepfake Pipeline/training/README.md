# Deepfake detector training notebooks (Colab)

| Notebook | What it does |
|---|---|
| `Fine_Tuning_XLS_R_for_AI_Deepfake_Detection_CAC_English_v2.ipynb` | The original training run (Oct 2026) that produced the deployed `best.pt` (SHA-256 `ae78eb6e…`). Saved with its outputs as the training record: MLAAD-tiny plus 21k extra MLAAD fakes, M-AILABS as the only real speech, split by TTS system, thresholds picked from float32 sigmoid outputs. |
| `Posttrain_XLS_R_Deepfake_CAC_v3.ipynb` | Robustness fine-tune that starts from that checkpoint. Adds LibriSpeech speakers (never `test-clean`), applies silence-gap, noise, background and codec augmentation equally to both classes, picks the best epoch by pooled multi-condition validation EER, and exports float64 logit thresholds plus a before/after report. |

The v3 notebook reuses the v2 cache on Drive (`MyDrive/CAC_deepfake_detector/cache_en`). Its last section lists the steps to bring the exported bundle into this repo:
1. Copy `detector_state.pt` and `detector_config.json` here.
2. Run `model_integrity.py --pin`.
3. Run the benchmark.
4. Update the release asset in `deploy/livekit/prepare.py`.

`notebook_selftest_fixture.py` builds synthetic stand-in data and a tiny random model, so the v3 notebook can run end to end on a CPU without network access:

```sh
python notebook_selftest_fixture.py /tmp/nbtest
CAC_NB_OVERRIDES=/tmp/nbtest/overrides.json jupyter nbconvert --to notebook --execute \
  --output /tmp/nbtest/executed.ipynb Posttrain_XLS_R_Deepfake_CAC_v3.ipynb
```

It checks plumbing only (every cell runs, and the bundle loads with `inference.py`). It says nothing about accuracy.
