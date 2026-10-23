# Independent validation utilities

These tools implement the data, calibration and release portions of both plans.
The five available sources remain **development** data (three supplied
ElevenLabs files and two human controls). All 18 original names
and their source lineage are in `data_manifest.json`. Final-test and calibration
sources have not been collected. Candidate regressions cannot establish accuracy.

From the repository root:

```sh
.venv/bin/python -m unittest discover -s 'model teseting/validation' -p 'test_*.py' -v
.venv/bin/python 'model teseting/validation/manifest.py' 'model teseting/validation/data_manifest.json' --verify-audio
.venv/bin/python 'model teseting/validation/calibrate.py' audit 'backend/AI Deepfake Pipeline/detector_config.json'
.venv/bin/python 'model teseting/validation/release_gate.py'
```

The last command intentionally exits **2** until all release requirements are
met. Exit 0 is reserved for an actual passing frozen release evaluation.
`release_status.json` saves the initial blocked result. Each later output must
use a new filename (`--output` creates exclusively).

`manifest.py` rejects leakage through source, speaker/system group or audio hash,
unknown lineage, and unverified held-out provenance. Use `--verify-audio` to
verify actual bytes; routine validation need not read private recordings.

`calibrate.py fit` consumes a list of `{source_id, logit, checkpoint_sha256}`
records and a validated manifest. Every registered calibration source must have
an outcome. It refuses development/final-test data and gives every source equal
total weight regardless of window count. It writes a candidate float64 Platt
artifact without changing production. Example, after independent collection:

```sh
.venv/bin/python 'model teseting/validation/calibrate.py' fit \
  --manifest /absolute/path/to/frozen-manifest.json \
  --scores /absolute/path/to/calibration-logits.json \
  --checkpoint-sha256 VERIFIED_64_CHARACTER_SHA256 \
  --output /absolute/path/to/new-calibration.json
```

The artifact does not claim population calibration. Operating points still
require calibration selection, a frozen candidate and independent final testing.
No training data or notebook for this voice checkpoint was found in this checkout;
the `backend/jev-posttrain` model is a different transcript classifier.

`release_gate.py` consumes registered final-test calls. Each row has `source_id`,
five explicit boolean outcomes (`human_false_headline`, `human_false_warning`,
`ai_missed`, `ai_deadline_missed`, `analysis_uncovered`), numeric
`human_with_fresh_warning_sec`, and an ordered `transitions` list of
`{target, delay_sec}` matching the manifest. Not-applicable class outcomes must
be explicit false. Unknown/missing outcomes fail closed and count as failures.
Call rows sharing leakage groups require an independently specified clustered
analysis and cannot be fed to this independent-binomial gate. Source metadata
`human_speaker_id`, `synthetic_voice_id`, `synthetic_system_id` supports coverage.

Each required check needs `{status: "passed", artifact: "/absolute/path", sha256}`
with a real matching artifact. `frozen_bundle` binds checkpoint, architecture,
policy and source SHA256 hashes and the canonical JSON manifest/specification
hashes (sorted keys, compact separators). Hardware, phone-path and physical
iPhone checks cannot be replaced by mock or offline results.

Read `data_policy.md` for collection, symmetric degradation, consent, retention,
independence, timing, rollout and rollback requirements. `release_spec.json`
records targets before candidate evaluation; those targets have not been met.
