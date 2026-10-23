# JEV V6: legitimate partial conversations

The user's objective is fewer real-world errors. No finite benchmark can prove
100% accuracy on arbitrary future calls. This experiment makes no such claim.

Protocol written while V6 training was running, before evaluating either model
on the new 100-call sample.

- Start from V5, retain recorded scam/normal examples, synthetic replay, banking
  roleplay and authored contrast training. Add 771 benign prefixes from training
  calls only. The 103 new validation prefixes come only from validation calls.
- Train one epoch at learning rate 5e-7. Choose epoch zero or one by the existing
  equal-source validation NLL procedure. Do not tune on test results.
- Compare V5 and V6 at fixed 0.5 and 0.75 thresholds, in both tail and overlapping
  window modes. Primary guidance operating point is windows at 0.75.
- Freeze 100 additional banking-roleplay calls, excluding prior training,
  validation and probe call IDs and normalized exact transcripts. Preserve raw
  checksums and a frozen dataset hash. These calls never enter training or
  validation. Also evaluate their one-third and two-thirds prefixes separately.
- Before scoring, the character-ngram audit found 64/100 fresh calls at cosine
  similarity >=0.8 to a prior banking transcript (maximum 0.9886). Also report
  the remaining 36 lower-similarity calls separately; this threshold and their
  call IDs are saved before evaluation. They remain from the same roleplay
  source and do not constitute an independent real-world benchmark.
- Favor V6 only if fresh-call false alerts decrease without increasing recorded
  scam misses or false alerts in the existing banking/authored probes at the
  primary operating point. Report every comparison even if V6 fails this gate.
  Synthetic regression results and calibration metrics remain visible.
- Do not replace production weights as a consequence of a small development
  comparison. Local research artifacts are reversible and remain separate.

Sources: [Switchboard transcripts](https://github.com/cgpotts/swda),
[Harper Valley banking roleplay](https://github.com/cricketclub/gridspace-stanford-harper-valley),
and [FTC/NCSU recordings](https://github.com/wspr-ncsu/robocall-audio-dataset).
Banking roleplay is recorded speech, not organic banking traffic. New call IDs
from the same source do not establish independence of speakers or scenarios.
Natural conversations have context-derived benign labels; recorded scams have
silver labels. No independently adjudicated, source-diverse, prospective call
benchmark is present. Whole-call labels do not supply fraud labels for early
prefixes, so only benign prefixes are generated. Prefixes are not new calls.

Training-set builder: `backend/jev-posttrain/benign_prefix_training.py`.
Frozen-probe builder: `backend/jev-posttrain/fresh_banking_eval.py`.
Four data-construction tests cover exclusion of scam prefixes, parent linkage,
split leakage rejection and refusal to overwrite output. The builder succeeds
with no test file present.

Reproduction after preparing the existing V5 data and downloading the upstream
HVB recursive tree JSON:

```sh
.venv/bin/python backend/jev-posttrain/benign_prefix_training.py
.venv/bin/python backend/jev-posttrain/fresh_banking_eval.py --tree /tmp/callshield-hvb-tree.json
.venv/bin/python backend/jev-posttrain/finetune_real.py --model backend/jev-posttrain/runs/call-v5-balanced --output backend/jev-posttrain/runs/call-v6-prefix --epochs 1 --replay 600 --lr 5e-7 --extra-train backend/jev-posttrain/data/real_calls/benign_prefix_training/train.jsonl --extra-validation backend/jev-posttrain/data/real_calls/benign_prefix_training/validation.jsonl --domain-balanced-selection
.venv/bin/python backend/jev-posttrain/benchmark_real.py --baseline backend/jev-posttrain/runs/call-v5-balanced --baseline-name v5 --candidate backend/jev-posttrain/runs/call-v6-prefix --candidate-name v6 --fresh-probes backend/jev-posttrain/data/real_calls/fresh_banking_20261022/probes.jsonl --fresh-audit docs/testing/2026-10-22-jev/fresh-data-audit.json --output docs/testing/2026-10-22-jev/benchmark-v6.json
```

The prefix and fresh-probe builders refuse to overwrite their existing outputs;
reuse the frozen local files for reproduction. Input artifacts and checkpoint
binaries remain in ignored local research directories.
