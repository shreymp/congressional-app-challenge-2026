# Why V6 regressed, and what V7 should repair

Investigation completed October 22, 2026. This is a diagnosis of already-inspected
development data, not a new blind evaluation or a trained V7. No model, cutoff,
app bundle or running service was changed.

## Finding

V6 became more reluctant to flag fraud. Training added 771 benign prefixes and
no additional positive examples, while checkpoint selection rewarded a better
average loss without requiring scam recall to hold steady. The fixed 0.75
warning cutoff then magnified the score shift on a new distribution of short
human dialogue excerpts. The test also gives some excerpts whole-call scam
labels even when the excerpt itself contains little fraud evidence.

These are identifiable training, selection and measurement problems. There is
no evidence here that a larger model or another version number alone fixes them.

## Same-sample comparison, including V3

All numbers below use the same 50 scam-source and 50 normal-source human excerpts,
window inference and fixed 0.75 cutoff. V3 was newly evaluated for this diagnosis.

| Version | Correct / 100 | Scam excerpts detected / 50 | Missed scam excerpts / 50 | False alerts / 50 |
| --- | ---: | ---: | ---: | ---: |
| V2 | 65 | 29 | 21 | 14 |
| V3 | 69 | 19 | 31 | 0 |
| V5 | 67 | 17 | 33 | 0 |
| V6 | 60 | 10 | 40 | 0 |

Missed scams are failures to flag scam-labeled examples, so fewer is better.
V2 catches more scam excerpts but wrongly flags 14 normal ones. V6 is more
conservative than V3/V5, and gains nothing on this sample's already-perfect
normal classification while losing scam detections. Version numbers describe
successive experiments, not monotonic quality improvements.

## 1. Training overcorrected toward normal

Reconstructing the exact replay shuffle and counting augmentation:

| Training pass | Scam-labeled examples | Normal-labeled examples | Normal share |
| --- | ---: | ---: | ---: |
| V5 | 804 | 1,018 | 55.9% |
| V6 | 804 | 1,789 | 69.0% |

These are training presentations, not independent calls. V6's additional 520
Switchboard prefixes and 251 banking prefixes duplicate information from the
existing benign calls. The original 479 recorded training calls cover only three
selected scam families versus natural casual conversation. Replay remains mostly
synthetic. Neither this class balance nor its source coverage represents real
phone traffic.

V6 assigns lower scores than V5 to **all 50 scam excerpts and all 50 normal
excerpts**. Median scam score falls from 0.07888 to 0.01042; median normal score
falls from 0.002503 to 0.001438. This is strong evidence of a broad conservative
shift consistent with the training change. It is not a controlled ablation that
isolates class balance from every other optimization effect.

## 2. Checkpoint selection had the wrong guardrails

`finetune_real.py` selects the checkpoint with the lowest equal-source validation
NLL. V6 treats benign banking prefixes and benign Switchboard prefixes as two
additional validation sources, even though they derive from calls in sources
already counted. Four of its seven source groups are purely benign; one is purely
scam, with only five recorded scam validation examples. The two remaining sources
are mixed synthetic/authored examples.

The V6 selector improves from 0.07387 to 0.03735, yet the 0.5 validation false
negatives rise from 2 to 4 while false positives fall from 10 to 2. The selection
code contains no minimum scam-recall requirement. This allowed a checkpoint that
was better by the selected average objective but worse for warning on scams.
The pre-existing synthetic regression test subsequently confirms increased misses.

This was a flaw in the experiment design. Benign prefixes should not acquire
independent-source status merely because they have a new source-name suffix.
More independent scam evidence and explicit recall constraints were needed before
another benign-heavy training pass.

## 3. The cutoff hides considerable ranking ability

Scores are experimental risk values, not field-calibrated scam probabilities.
The 0.75 warning cutoff was a declared product setting, not a threshold selected
on representative human-dialogue validation. Temperature scaling was fitted on a
small mixed validation collection. Window maximum pooling is also not calibrated
by that tail-mode fit.

| Version | ROC AUC on these 100 excerpts | Best single-cutoff correctness **after inspecting the answers** |
| --- | ---: | ---: |
| V2 | 0.7408 | 68/100 |
| V3 | 0.9800 | 94/100 |
| V5 | 0.9796 | 95/100 |
| V6 | 0.9636 | 93/100 |

AUC measures ranking across scam/normal pairs; it is not accuracy or a field
success percentage. The V5 value means it ranks a scam excerpt above a normal
excerpt in about 98% of this sample's cross-class pairs. V5 therefore has much
better ranking than its 67/100 result at 0.75 suggests.

The post-hoc V5 cutoff is approximately 0.00887, catching a different region of
the uncalibrated score distribution. **It must not be installed as a validated
fix.** It was selected using the very test answers we want to predict, and the
negative class here is casual conversation, not difficult legitimate banking or
emergency calls. It demonstrates that 95/100 is attainable on this already-seen
sample by a changed decision rule, not that a new V7 achieves 95% independently.
The post-hoc best for V6 is worse than V5, so the regression is not entirely a
threshold issue: ranking also degraded.

Positive temperature scaling preserves ranking and the 0.5 decision boundary.
It cannot repair ranking errors or magically turn these scores into field
probabilities. [Guo et al., ICML 2017](https://proceedings.mlr.press/v70/guo17a.html)
provides the calibration baseline; these conclusions about this run also follow
directly from its sigmoid-margin implementation and measured scores.

## 4. The test cannot settle full-call correctness

The public YouTube corpus contains brief source-provided excerpts, not full
transcripts. Some excerpts only discuss ordinary account checks, software
troubleshooting, a refund form, or a pharmacy request. Their labels attribute
fraud to the source call; those labels do not establish that fraud can be inferred
from the supplied words. The earlier report disclosed this, but the headline
correctness table needs this qualification to be interpreted fairly.

The normal examples are casual recorded Switchboard conversations. They provide
neither the same source style nor the range of legitimate business interactions
seen in the scam class. The sample cannot separate source recognition, excerpt
sufficiency, imperfect labels and actual fraud recognition. It does not measure
audio transcription or live remote-speaker-only performance. Source-attributed
human recordings were not independently verified by listening to every video.

Scam-baiting is informative about scammer behavior but differs from unsuspecting
victim calls, as discussed by [Wood et al.](https://arxiv.org/abs/2307.01965).

The model's proposition asks for a whole-call verdict, but its fine-tuning target
only supplies true/false. No row targets the available insufficient-evidence
label. Runtime risk scoring also reduces inference to the true-versus-false
margin; the service's explicit abstention is a short-greeting check. Ambiguous
early prefixes do not have independently annotated unknown labels. That is
another task-design mismatch for early-call safety guidance.

## 5. Checked alternatives

- Confusion counts and labels were independently read back from the 100-row sheet
  and all 300 prior model predictions; there is no swapped meaning of missed
  scams versus correct detections.
- Changing the input prefix from `Conversation:` to `Caller:` improves V5 from
  67 to 70 correct and V6 from 60 to 63, with no false alerts. This formatting
  sensitivity is real but does not explain the main gap. Removing the prefix
  leaves the original 67 and 60 results unchanged.
- Only 2/100 inputs exceed 300 tokens, with maximum length 322. Window mode covers
  them. Truncation is not the main explanation for this particular sample.
- V3, V5 and V6 were evaluated from existing saved checkpoints, with no training
  on this investigation's answers. No claim about a base-model capacity ceiling
  or catastrophic loss of its original general decision task is established.

Full measurements, source-group validation losses, training counts, score
quantiles and ablations: [diagnostics.json](diagnostics.json).

## V7 repair specification

1. Start with V3/V5 as measured baselines. Test a revised decision/calibration
   layer before changing all model weights. Fit it on a separate, source-diverse
   human validation set with both genuine difficult negatives and scams. Select
   the operating point using an explicit false-alert budget and scam-recall
   requirement. Freeze it before a new independent test.
2. Obtain longer human calls and separate the remote caller from the baiter or
   narrator. Label whether each prefix actually contains sufficient evidence.
   Keep source-call fraud labels separate from prefix evidence labels. Use
   trainable uncertainty/abstention only with defensible labels and report its
   coverage alongside errors.
3. If more weight training is needed, preserve effective scam/normal balance,
   sample at the parent-call level, and divide a call's weight across its derived
   prefixes. Do not give duplicate prefix domains extra validation votes. Include
   human scam varieties outside the current three recorded fraud families and
   legitimate business calls with similar words.
4. Reject a new checkpoint if validation scam recall deteriorates beyond the
   predeclared bound, even when average NLL improves. Verify both false alarms
   and misses by source and scenario, plus ranking and calibration. Enforce these
   gates during selection, before inspecting test results.
5. Split by source/creator, speaker, call and scam script where feasible. Keep
   these 100 already-inspected examples as development diagnostics; never claim
   success on them as newly held-out 90–100% performance. A fresh labeled test
   must decide whether the changes generalize.

A V7 name cannot guarantee 90 or 100 correct future calls. The evidence supports
repairing the decision rule, training balance, selection criteria and evaluation
labels before running another full-model pass. Training until the current 100
answers are memorized would answer the wrong question.

Reproduce the read-only diagnosis with:

```sh
.venv/bin/python backend/jev-posttrain/diagnose_versions.py
```

The script refuses to overwrite its output directory. Its threshold sweep is
explicitly tagged as a post-hoc test diagnostic and does not save a deployment
configuration or retrain any model.
