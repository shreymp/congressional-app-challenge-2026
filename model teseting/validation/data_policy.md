# Evaluation data and release protocol

Created October 22, 2026, before running the new candidate experiments. The
existing 18 cases have already informed development. They cannot be moved to
calibration or final test, even under a new filename, codec, crop, or speaker mix.

## Collection and partitions

`data_manifest.json` describes the available sources and every original regression
case. No new consent or synthetic-voice identity is inferred from a filename.
The original supplied ElevenLabs clip is labeled synthetic by the supplied evaluation;
clone identity, recording permission, generation settings, and training overlap
remain unverified. Two additional user-directed ElevenLabs files in Downloads
(azim and keshav in their filenames) are supplemental development sources from
the same system, with unverified identities and rights. The two LibriSpeech readers are licensed development controls,
with unknown model-training overlap. There are currently zero independent
calibration or final-test calls.

Collect at least 30 human speakers and 10 synthetic voices across three systems
as an initial coverage milestone. Include older adults, women, accents, languages,
natural conversation, quiet speech, microphones, and real phone paths. These
counts are coverage goals, not proof of statistical adequacy. Record a human
and a consented clone reading the same script on the same microphone/codec to
separate voice identity and recording format from synthesis.

Assign source recordings, speakers, sessions, clone identities, and synthetic
systems to development, calibration, or final test **before** scoring. All
derivatives inherit all parent groups and stay together. Hold out complete TTS
systems for generalization. The validator rejects cross-partition reuse of
source/group identifiers and audio hashes; it cannot discover mislabeled
identities, so a human provenance review is also required.

Collect the training notebook and validation data. Resolve validation/test
distribution and speaker/system overlap before interpreting the checkpoint's
reported EER. Fit calibration in float64 raw-logit space on calibration calls
only, with each independent call receiving equal total weight. A successful
numerical fit does not establish calibration on a different phone domain.
No present threshold or calibrated probability is justified by these five sources.

## Symmetric phone-domain conditions

Apply the same transform and seed distribution to both classes: clean,
300–3400 Hz, real G.711 mu-law/A-law, deployed Opus/MP3 codecs, +/-20 dB level,
noise 0–20 dB SNR, clipping, reverberation, packet loss, echo, and background talk.
Measure achieved levels and clipping. Synthetic white/pink noise, tones and
generated music are engineering controls; they are not recorded hold music or
TV. Record codec tools/versions and distinguish unsupported conditions from
passing ones. Do not train a detector on a class/codec confound.

## Frozen release criteria

`release_spec.json` records conservative engineering targets before candidate
selection. They are explicit project targets, not validated operating points.
Thresholds, horizon, gating, and model changes may be explored on development
data; choose and freeze exactly one bundle before final testing. Hash the
bundle, manifest, specification, code and dependencies. Final-test failure
requires a new version and a newly reserved test set, not repeated cutoff tuning.

The release gate treats missing, abstained, rejected and canceled calls as
unresolved outcomes. A call containing human speech is falsely warned if either
the headline or the current warning falsely warns at any time in a labeled human
interval. Report those two event types separately as well as their union.
Calls containing AI are missed if no qualified warning or AI assessment occurs
in the labeled AI interval. A warning during an earlier human interval cannot
count as detecting a later AI interval. Report each transition independently.

Do not multiply sample size by windows or transformations. The automated gate
accepts one registered independent unit per row and rejects reused source or
speaker groups. For broader sets with repeated speakers, use a preregistered
cluster-level analysis rather than feeding all calls to a binomial calculation.
Report one-sided exact 95% binomial upper bounds for failure proportions; zero
observed human false warnings requires at least 299 independent human units to
bound the rate below 1%. Keep per-condition, language, and source counts visible.

## Retention and logging

Operational logging contains call/stream/window identifiers, local monotonic
durations, quality, stage and counters. Routine logs contain neither audio nor
transcripts. Evaluation raw logits are linked to pseudonymous IDs and remain in
the evaluation workspace. Audio capture defaults off. Enable it only for a
specific consented evaluation, announce recording before caller analysis, store
outside Git, restrict access, and record deletion dates. Use a 30-day initial
retention period unless the recorded consent requires an earlier deletion.
Record deletion without keeping identifying content. Never infer consent from
possession of a file. External collection and phone calls remain unexecuted.

## Live acceptance and rollout

1. Run Python orchestration, malformed/legacy/v2 packets, Swift contract,
   XCTest and UI/simulator checks with outcomes saved separately.
2. On the actual deployment device, measure cold/warm startup and one/multiple
   calls. Pin checkpoint, architecture, preprocessing, calibration and policy.
3. On consented physical calls, correlate connection, disclosure start/end,
   first caller audio, sufficient speech, submission/completion, publish,
   receive and displayed events by call/stream/window ID. Preserve disclosure
   gating and the 15-second connection deadline. Use within-process monotonic
   intervals; cross-device timing needs measured clock-offset uncertainty.
4. Test unavailable detector, delayed result, out-of-order publication, stream
   restart, heartbeat loss, interruption and late recovery. Distinguish a saved
   previous result from fresh analysis. Report p50/p95, coverage and failures.
5. Shadow candidate/reference without duplicate user warnings. Label the
   disagreements independently. Keep the presentation contradiction fix in
   both versions; enable current-evidence and quiet-gate changes separately.
6. Block release until `release_gate.py` passes the frozen held-out call metrics
   and every required actual-device check. Exercise rollback to the compatible
   v1 path with candidate flags disabled and confirm warning presentation stays
   safe. Do not call a local replay a deployment or an actual connected call.
