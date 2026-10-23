# 100 human conversation tests, October 22, 2026

**Completed: 50 YouTube human scam-baiting conversation excerpts and 50 natural
human telephone conversation excerpts.** No synthetic dialogue, banking roleplay,
FTC robocall probes, or voice-agent honeypot conversations were used. These are
transcript tests of source-attributed recorded human conversations. No new audio
was downloaded or transcribed, and every original video was not independently
listened to. The results do not establish full-call, live-call or field accuracy.

## Results

The frozen primary setting is overlapping windows with warning threshold 0.75.
All 100 conversations are scored once per model, using existing saved weights
and calibration. No weights, thresholds or labels were fitted to these tests.

| Model | Correct / 100 | Scam excerpts detected / 50 | Missed scam excerpts / 50 | False alerts on normal excerpts / 50 |
| --- | ---: | ---: | ---: | ---: |
| V2, currently bundled model | 65 | 29 | 21 | 14 |
| V5, preferred local research model | 67 | 17 | 33 | 0 |
| V6, latest benign-prefix experiment | 60 | 10 | 40 | 0 |

At the separately declared 0.5 cutoff, V2 scores 62/100, V5 70/100 and V6 61/100.
Both cutoffs are reported; neither was chosen after seeing these results.
V5/V6 reduce normal-conversation false alarms but miss substantially more
scam-attributed excerpts than V2. The models are not close to 100% on this test.

The [100-row test sheet](100-tests.csv) includes each conversation's source URL,
source label, all three scores and correctness at 0.75. This is 100 distinct
conversation sources, evaluated by three models, not 300 independent calls.
[model-evaluations.csv](model-evaluations.csv) has the 300 individual model
evaluations. [results.json](results.json) includes confusion counts, Brier/NLL,
calibration metrics, thresholds, checkpoint hashes and dataset hashes.

## Sources and selection

The scam material is the public [YouTube Scam Phone Call Transcripts corpus](https://www.kaggle.com/datasets/rivalcults/youtube-scam-phone-call-transcripts),
also used by the [BYU-PCCL scam-call research pipeline](https://github.com/BYU-PCCL/scam-call-identification/blob/main/scripts/ETL/youtube_scam_calls_1/raw_data/get_data.py).
Its 243 rows contain short source-provided transcript excerpts, not complete
calls. A deterministic hash order selects 50 distinct YouTube video IDs from
eight named human scambaiting channels, with at most 12 per channel. FTC videos,
MoreKitboga, unknown channels, non-YouTube links and excerpts shorter than 45 words
are excluded. Included channels are ModderPaulScambaits, scambaittv, CJSCAMS,
ToniMosh, Jim Browning, ScammerAllergy, FunGuyMediaScambaits and
DanGleeballsScambaiter. A human scambaiter deliberately engages the caller; these
are not recordings of unsuspecting victims. Source attribution is not an
independent fraud adjudication or per-video verification of every speaker.

The normal material comes from the public [Switchboard Dialog Act corpus](https://github.com/cgpotts/swda):
recorded natural human phone conversations, not scripted banking roleplay.
Conversations and speakers used in earlier training, validation or evaluation
are excluded. No speaker repeats across the 50 new normal calls. The first words
of each normal conversation are length-matched to a corresponding scam excerpt
so the classes do not differ simply by excerpt length. Normal labels come from
the conversation context, not an independent fraud-label review.

Each selected source, video ID or archive member, known-data similarity and
provenance note is in [source-manifest.json](source-manifest.json). Raw transcript
text stays in the ignored local research data directory. Kaggle metadata lists
CC0 for its dataset; original videos retain creator rights. Switchboard corpus
terms apply. No raw corpus or creator audio is redistributed in these results.

## Audit and interpretation

- Frozen dataset hash: `134ed53d825ca25f6ac65bb03b8a091d7a56e21b4fc5341a7263702eda961476`.
- Exactly 50 scam-attributed video IDs and 50 natural conversation IDs.
- Zero prior normal speaker overlap; zero repeated normal speakers within this test.
- Zero normalized exact-text overlap with the checked earlier data, including
  original synthetic training and the later recorded/prefix training inputs.
- Maximum character-ngram similarity to checked known text: 0.6166; no new
  excerpt reaches 0.8. This does not prove semantic independence or rule out
  unknown upstream/base-model pretraining exposure.
- No test-driven training, re-labeling, threshold changes or resampling was done.
- An independent readback checks the 100-row sheet, all 300 predictions, exact
  class counts, confusion counts, unique sources and frozen dataset checksum.

**The label describes the source call, while the model only sees its short
excerpt.** Many scam-source excerpts contain routine greetings, troubleshooting
or account questions and end before a money demand or other decisive evidence.
A low score can therefore mean insufficient evidence in the supplied excerpt;
the aggregate missed-call count cannot isolate classifier failures from missing
context or imperfect source labels. The test still exposes how little support
there is for claiming reliable early scam detection from these snippets.

Conversely, perfect performance on these 50 natural casual conversations does
not establish low false alarms on legitimate banking, medical or emergency
calls. Classes come from different sources, and YouTube publication, editing,
repeated creators and overlapping scam scripts introduce sampling bias. These
mixed-speaker excerpts also differ from the app's remote-speaker-only input.
No abstentions were removed from the denominator. Short greetings are excluded
by source selection, so this test does not measure greeting-abstention coverage.

No app model was replaced. V5 remains a research candidate, and V6 is not promoted.
The next evidence needed is independently labeled, longer human call transcripts
with early-prefix labels and speaker separation, plus new held-out sources. The
100 tested examples must remain evaluation-only for this comparison; training
on their answers would invalidate a later claim of independent improvement.

## Reproduction

`backend/jev-posttrain/human100.py` builds and scores the frozen sample. It refuses
to overwrite the dataset or output directory and verifies the dataset hash before
inference. It neither downloads data nor trains models itself. Obtain the public
Kaggle archive and Switchboard repository archive from the links above, then:

```sh
.venv/bin/python backend/jev-posttrain/human100.py build --scam-zip /tmp/jev-youtube-scam-transcripts.zip --swda-zip /tmp/callshield-swda.zip
.venv/bin/python backend/jev-posttrain/human100.py score
```

Existing frozen data and weights remain local. To repeat scoring, supply a new
`--output` directory; retain the original dataset. All model calibration and
checkpoint hashes used in this run are preserved in the results.
