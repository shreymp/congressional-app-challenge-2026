# JEV V6 experiment, October 22, 2026

**100% real-world accuracy was not achieved or established.** A new V6 checkpoint
was actually trained and evaluated. It reduces selected benign false alarms but
regresses on scam recall, so it does not replace V5 as the preferred research
candidate. The deployed and bundled models were not changed.

## Results

At the fixed 0.75 guidance threshold, with overlapping windows unless specified:

| Evaluation | V5 | V6 |
| --- | ---: | ---: |
| Missed scams, selected recorded text | 0/10 | 0/10 |
| False alerts, natural recorded conversations | 0/21 | 0/21 |
| False alerts, prior recorded banking roleplay | 1/40 | 0/40 |
| False alerts, authored difficult benign contrasts | 3/13 | 2/13 |
| Missed scams, authored contrasts | 0/12 | 0/12 |
| Errors, six existing public audio/Vosk probes | 0/6 | 0/6 |
| False alerts, 100 newly reserved banking roleplays | 0/100 | 0/100 |
| False alerts, 154 partial transcripts of those calls | 3/154 | 0/154 |
| False alerts, 36 lower-similarity reserved calls | 0/36 | 0/36 |
| Missed scams, earlier synthetic-style test, **tail mode** | 7/650 | 16/650 |
| False alerts, earlier synthetic-style test, **tail mode** | 0/650 | 0/650 |

At the separate 0.5 binary cutoff, earlier synthetic test accuracy drops from
1294/1300 to 1291/1300. Tail-mode and window-mode results for all collections,
including Brier/NLL/calibration errors, are in [benchmark-v6.json](benchmark-v6.json).
The 0.75 guidance threshold is an experimental policy, not a verified 75% chance
of fraud. Scores after window maximum pooling do not inherit tail calibration.

The [protocol](PROTOCOL.md) required a strict reduction in false alerts on the
new full-call sample without worse recorded misses or existing probe false
alerts. Full-call false alerts were already zero for V5, so this gate fails.
The synthetic recall regression gives another reason not to promote V6.
[decision.json](decision.json) records this explicitly. No additional training
or threshold tuning was performed after these evaluation results.

## What was trained

V6 starts from the existing V5 weights. Training retains 479 recorded examples,
479 ASR-style augmentations, 600 earlier synthetic examples, 160 recorded banking
roleplays and 104 authored examples. It adds **771 partial benign transcripts**
derived exclusively from the existing training calls. These are not 771 new
recordings. Only benign prefixes inherit a label; early scam prefixes are not
given a fraud label from their whole conversation.

One epoch was run on the local Mac GPU at learning rate 5e-7. Validation selects
epoch one using equal-source NLL: 0.07387 before training, 0.03735 afterward.
The expanded validation set has 551 examples, including 103 benign validation
prefixes. At 0.5 its false positives fall from 10 to 2, while false negatives
rise from 2 to 4. The fitted temperature is 2.33185 and is limited to this mixed
validation distribution. It is not real-world probability calibration.

Saved checkpoint: `backend/jev-posttrain/runs/call-v6-prefix/model.safetensors`.
It is a local trainable research checkpoint, not an exported or app-installed
model. [train-manifest.json](train-manifest.json) preserves the training details;
the benchmark records V5/V6 checkpoint hashes. Raw transcripts, individual
predictions and checkpoint binaries remain in ignored local research folders.

## How much evidence this provides

The 100 additional banking transcripts were reserved before scoring and do not
overlap earlier banking training, validation or probes by call ID or normalized
exact text. Their [frozen manifest](fresh-manifest.json) records the checksum.
However, [the similarity audit](fresh-data-audit.json) found **64/100** closely
resemble an earlier banking transcript at character-ngram cosine >=0.8. The 36
less-similar calls were identified before scoring and reported separately.
All are from the same recorded roleplay source; speakers/scenarios may overlap.
They are not organic bank traffic or a source-independent benchmark.

The 154 prefixes share those same 100 parent calls and cannot be counted as
independent additional calls. The 36-call subset is also part of the 100-call
sample; do not add these denominators together. No fresh scam calls or new audio
were collected in this experiment. The six audio probes reuse previously
transcribed recordings. Existing development tests were repeatedly inspected
during earlier V3–V5 work. The recorded scam sample still contains only ten
recordings from four script groups, with silver labels.

The [recorded split audit](data-audit.json) passes exact-text, script-group and
speaker separation checks. Four new construction tests pass, covering exclusion
of scam prefixes, parent linkage, leakage rejection, no test-file dependency and
refusal to overwrite frozen outputs. Compilation and whitespace checks pass.

These results show a specific benign-prefix improvement and a measurable scam
recall regression. Establishing better field performance requires additional
independently reviewed legitimate and fraudulent calls, new sources and speakers,
and a prospectively frozen evaluation. A transcript also cannot establish whether
a caller's identity or an ordinary-sounding story is true.

Public source descriptions and earlier evidence are linked in
[the protocol](PROTOCOL.md) and [the V3–V5 report](../2026-10-20-transcript/REPORT.md).
