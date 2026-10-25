# V4 training (ElevenLabs-targeted, self-correcting)

`Posttrain_XLS_R_Deepfake_CAC_v4.ipynb` continues training **V3** in Colab (L4 or A100). The notebook's first cell explains everything. In short:

**Before you run it**, put these in `MyDrive/CAC_deepfake_detector/`:

| Path | What |
|---|---|
| `cache_en/`, `cache_extra_real_v3/` | Already there if V2 and V3 ran |
| `export_posttrain_v3/detector_state.pt` | V3 (SHA-256 `c634c95b…`) |
| `ckpt_en/best.pt` | Optional: V2, comparison table only |
| `benchmark_audio/` | The 5 files from `../Compare V2 and V3/inputs/audio/` |
| `external/elevenlabs_respeecher_mendeley/` | **Strongly recommended:** unzip <https://data.mendeley.com/datasets/79g59sp69z> here (CC BY 4.0; language not stated). Without it, V4 has to train on 2 of your 3 voices and test on the third. |
| `own_data/real/<speaker>/` | Optional: consented real recordings (e.g. the audio your clones were made from) |

**What it does differently from V3:**
- ElevenLabs/Respeecher clips in training, split by voice
- a noisy-twin consistency loss for the white-noise collapse
- one-sided distillation from frozen V3, so V4 can't get worse on human speech or other TTS than V3 was
- an anchor to V3's weights
- label-blind MP3 and band-limit augmentation
- selection on ElevenLabs detection at 2% false flags

**The Guardian** checks validation about 3× per epoch. If any metric drops below V3 or the best accepted state, it:
1. rolls back
2. halves the learning rate
3. retunes the knob tied to what broke
4. logs the decision to `self_correction_log.json`

Test data and the benchmark are scored once at the end. A **release gate** sends the export to a `…_CANDIDATE_DO_NOT_DEPLOY` folder if V4 is worse than V3 on any test metric.

**Checked before delivery (October 23, 2026):** the notebook ran end to end on CPU in `SMOKE_TEST` mode with the real V3/V2 weights, your 3 ElevenLabs MP3s and the benchmark files, plus tiny stand-in caches. Covered:
- both data modes (own-voices fallback and external, with a stand-in metadata spreadsheet)
- a Guardian rollback (one real, one forced) and an accept
- resume from Drive
- the release gate, the benchmark table and export

Because CPU RAM was limited, the self-test trained only the classifier head (`_TEST_TRAIN_HEAD_ONLY`). The full-backbone path runs on the GPU and hasn't been run yet. The smoke numbers mean nothing (fake data, 4 steps). No real training result exists yet.
