# JEV V7 repair: guarded training and separate warning-policy validation

October 22, 2026. Local research work. No app bundle, running service or published
checkpoint was replaced.

## Changes implemented

The V6 failure was allowed by three mechanisms: excessive weight for derived
normal examples, extra validation votes for prefixes of existing domains, and
selection by average loss without protecting scam detection. Those mechanisms
are now changed in `backend/jev-posttrain/finetune_real.py` and
`training_safety.py`:

1. **Class/call balancing.** Scam and normal classes each receive half the total
   training weight. A parent call divides its weight among its full text, ASR
   augmentation and any prefixes. Adding 100 prefixes no longer gives that call
   100 times the weight. Presentations remain distinct views, not new calls.
2. **Original-domain validation.** Prefixes stay in their parent source. Loss is
   averaged within each parent, then within each original source; it is not
   averaged across artificial prefix-source names.
3. **Mandatory regression gates.** An epoch cannot replace its starting checkpoint
   if it adds missed scams or false alarms at either .5 or .75, overall or in an
   original validation domain, using either tail or window inference. Parent
   calls count once, with an alert on any tested variant counting as an alert.
   Temperature stays fixed during this comparison. Lower loss alone cannot
   override these gates.
4. **Preservation and split auditing.** Epoch zero is retained if no improved
   epoch passes. Existing run directories cannot be overwritten. Known parent,
   script-group, speaker and normalized-text overlap across training and
   validation causes an error. Later runs also record the selected weight hash.
5. **Separate operating-point fitting.** `repair_eval.py` fits warning cutoffs on
   validation only, subject to at least 90% scam recall and no more than 5% false
   alerts in each benign validation domain. An infeasible fit produces a failed
   policy with no threshold. Both model policies are persisted before fresh-test
   inference. Evaluation output cannot be overwritten by another run.
6. **Bound policies at manual inference.** `score.py --policy` rejects failed
   policies and mismatched weights, tokenizer, temperature or context mode. It
   rejects nonfinite cutoffs and returns `alert`/`no_alert`, not a statement that
   a caller is safe. The ordinary scorer now also reads the checkpoint's own
   calibration file instead of silently using temperature 1 for later versions.

The existing V5 model was the starting point because diagnosis showed strong
ranking on the inspected sample. Restarting from upstream JEV is supported via
`finetune_real.py --model verdict-151m`, but there is no evidence that discarding
V5's useful learning would solve source coverage or label problems.

## Training experiments

The first guarded attempt used the same 771 additional benign prefixes that
motivated V6, now with corrected call/class weights, one epoch at 5e-7. It had
2,593 training presentations from 1,341 identified parents (583 scam, 758 normal),
with equal effective class weight. All audited train/validation overlap counts
were zero. Validation still contains mostly synthetic replay and silver labels.

Average row-level validation accuracy improved from 539/551 to 544/551, while
missed scams increased from 2 to 4 at .5 and from 4 to 6 at .75. Parent/domain
loss fell from 0.09537 to 0.04944. **The new gates rejected the epoch**, including
the new miss on the recorded scam domain at .75. V5 was retained. This is the
actual failure mode that the old selector could have accepted.

The second, smaller experiment removed the additional benign training prefixes
and used one epoch at 1e-7. Its training inputs still include original recorded
calls, synthetic replay, banking roleplays, authored contrasts and ASR-style
augmentation. It is not training on newly collected human scam calls. Both new
human evaluation splits and the old human100 were excluded from gradients and
epoch selection. The first experiment and an earlier serialization-error run
were preserved in separate local directories.

The second experiment also failed: .5 validation misses increased from 2 to 4,
and .75 misses from 4 to 5, despite a loss improvement to 0.06912 and fewer false
alerts. It was rejected. The selected epoch in both experiments is **epoch zero**.
The final local V7 research directory therefore retains exactly V5's weight hash;
it is not a successfully improved V7 checkpoint. Evidence:
[training summary](training-summary.json),
[prefix attempt](prefix_attempt-training.json),
[smaller refinement](smaller_refinement-training.json).

## Separate validation and fresh-test protocol

The protocol and transcript checksums were written before scoring these new
evaluation examples. [Protocol](protocol.json), [source manifest](source-manifest.json).

- Cutoff validation: 20 new YouTube scam-source excerpts, 2 new natural
  Switchboard excerpts, 18 explicitly reused normal training-validation calls,
  and 32 previously used banking roleplay validation calls. The reused examples
  are not counted as new human recordings. Total: 72 validation rows.
- Fresh test: 30 new YouTube scam-source excerpts and 30 new normal excerpts
  (28 Santa Barbara conversations and 2 Switchboard calls). No test call IDs
  overlap cutoff validation or the earlier human100. The selected scam videos
  are distinct, and selected scam transcripts with character-ngram similarity
  at least .8 to prior known call data or another selected transcript were
  excluded before scoring.
- New calibration scams come from ModderPaulScambaits; new test scams come from
  other named creators. These creators appeared in the previously inspected
  development sample, so this is not a completely unseen-creator study.
- Only four fully unused Switchboard speaker pairs remained among the available
  transcripts. A larger initial split was abandoned during data preparation,
  before model evaluation. No test scores or requirements were used to make
  that change. All four selected pairs are speaker-disjoint from known prior
  calls and each other. Santa Barbara was added as a new normal source.

Source links: [YouTube transcript corpus](https://www.kaggle.com/datasets/rivalcults/youtube-scam-phone-call-transcripts),
[Switchboard release](https://github.com/cgpotts/swda),
[UCSB Santa Barbara corpus](https://www.linguistics.ucsb.edu/research/santa-barbara-corpus-spoken-american-english).
Santa Barbara corpus citation: Du Bois et al., 2000–2005, *Santa Barbara corpus
of spoken American English, Parts 1–4*. UCSB licenses the corpus under CC BY-ND
3.0 US. It is used only for local evaluation; neither original nor processed
transcript text is redistributed or included in training.

## Actual cutoff and fresh-test results

Neither the V5 baseline nor the retained V7-directory checkpoint has a validation
cutoff meeting both requirements. With false alerts held to at most 5% per benign
domain, maximum scam recall is **13/20 (65%)**. Catching at least 18/20 requires a
cutoff that falsely alerts on **19/32 banking roleplays (59.4%)**, as well as 3/18
of the reused natural validation calls. This is a validation tradeoff, not an
independent field-performance estimate. Both policy files have `passed: false`
and `threshold: null`; the scorer was exercised with the failed V7 policy and
correctly refused to produce a decision.

At the unchanged .75 cutoff, the fresh 60-example test yields:

| Selected research weights | Correct | Detected scam excerpts | Missed scam excerpts | False alerts |
| --- | ---: | ---: | ---: | ---: |
| V5 / retained baseline in V7 directory | 38/60 (63.3%) | 8/30 | 22/30 | 0/30 |

On the old inspected human100, the retained weights reproduce 67/100, with 33
misses and zero false alerts. V5 and the V7-directory scores are identical because
the rejected epochs did not replace V5. There is **no accepted new operating
policy, no improved model checkpoint and no 90% or 100% result**. The fresh test
is now spent for future model/threshold selection.

[Full results](evaluation/results.json),
[320 scored rows](evaluation/predictions.csv),
[validation scores](evaluation/validation-scores.csv),
[policies frozen before test inference](evaluation/policies-frozen-before-test.json).
The 320 rows are two identical retained-weight evaluations of 60 fresh plus 100
previously inspected examples; they are not 320 distinct conversations. Counts
were independently recomputed from the CSV, and dataset and weight hashes checked.

## Verification and ongoing checks

Seventeen local tests pass, covering prefix/class weighting invariance, parent
and source aggregation, overlap rejection, additional misses despite improved
loss, per-source regressions, infeasible cutoffs, nonfinite outputs and policy
integrity. Python syntax and whitespace checks pass. A new
`.github/workflows/jev-training-safety.yml` runs those tests for future pushes and
pull requests touching this pipeline, without model weights or source recordings.
That workflow has been added locally; no remote CI run or push is claimed.

The actual two training runs demonstrate that a better average loss with more
missed scams is now rejected automatically. The weights remain research-only and
the app model is unchanged. The remaining blocker to higher accuracy is the
training/evaluation evidence and source coverage described below; the automatic
checks prevent accepting measured regressions rather than manufacturing quality.

## What these checks do and do not establish

These checks stop the measured V6-style validation regression from silently
becoming the selected checkpoint. They cannot guarantee that future real-world
calls will never regress. The same validation collection can also become overfit
through repeated experiments; it must be refreshed and a new final test reserved
for later development.

The YouTube labels attribute fraud to the source call. They are not independent
human judgments that each short excerpt contains enough evidence of fraud. The
videos were not individually listened to for this study. Scambaiting differs
from calls with unsuspecting victims. The normal class comes from other sources;
Santa Barbara includes mostly face-to-face interactions, not ordinary phone
traffic. Some Santa Barbara speakers may recur across its selected recordings.
Source/style recognition remains a confound. There is no IID confidence or
field-accuracy claim here.

No full audio-call, ASR, remote-speaker-only or native model parity improvement
is established. Positive scam prefixes were not assigned invented early fraud
labels. Properly supervised uncertainty still requires independently adjudicated
prefix evidence; these changes do not pretend to train that missing capability.

The outstanding data work is longer human calls with speaker separation,
independently reviewed scam-evidence onset/uncertainty labels, and diverse
legitimate business/emergency calls that resemble scams. A fresh test of that
material is needed before deploying a stronger model or claiming 90–100%.
