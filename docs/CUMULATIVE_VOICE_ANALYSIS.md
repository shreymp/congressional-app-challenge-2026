# Shrey feature: cumulative voice analysis and 15-second initial assessment

## Branch and scope

`shrey` was fast-forwarded from `2f27d4d` to main's `dca989c` before implementation.
This incorporates all 39 intervening commits without discarding unique work.
Feature label: `deepfake / cumulative-voice-v1 / 15-second-initial-verdict`.
Changes are to the LiveKit worker's audio/scoring path, versioned room evidence,
the production iOS call screen, session deadline handling, and regression tests.
No model weights, transcript classifier, cloud secrets or production deployment
are changed. The separate recording-notice branch is not merged by this feature.

## User-visible behavior

The clock starts on the app's real `connected` event, after media becomes ready,
not when an incoming invitation rings and not after 15 seconds of voiced speech.
The screen immediately says **Analyzing**. Eligible model results can produce a
verdict before the deadline. At 15 seconds, an independent cancellable iOS task
finalizes any remaining waiting/analyzing state as **Inconclusive**. The call view
also derives this state from connection time when rendering, including on resume.
This is a UI deadline, not a promise that network/inference always finishes in 15s.

**Human**, **Likely AI**, and **Inconclusive** use the same **AI score: N/100**.
The score measures relative AI evidence, not human confidence or a probability.
No result means **AI score unavailable**; it never defaults to 0 or 50. Explicit
worker/transport failures show **Analysis unavailable**. Existing timeout behavior
still marks lost agent heartbeats unavailable after 12 seconds.

The initial result is provisional. Later evidence can revise it. A pause leaves
the score/verdict intact. A later warm-up heartbeat cannot erase an established
result. Genuine failure statuses remain visible with the last completed result.
Scores and recent-warning metadata survive saving the call in history. Historical
records without these optional fields remain decodable.

## Exact scoring implemented in this version

1. Buffer **contiguous four-second audio windows**. Natural pauses remain inside
   the window. The existing RMS gate (`0.01`) estimates voiced frames; a window
   needs at least 1.5 seconds of estimated speech and no more than 5% of samples
   at absolute amplitude 0.99 or above. This is an energy gate, not a trained VAD
   or comprehensive audio-quality estimator. Loud background noise can pass it.
2. Score a window only after at least four seconds of new samples since the
   previous submitted window. No samples are intentionally counted twice.
   Slow inference skips windows rather than building an unbounded work queue.
   Nonoverlap does not imply statistical independence.
3. Use the raw detector logit `z`. Let `a = logit(threshold_eer)` and
   `b = logit(threshold_1pct_fpr)`. Define
   `center = (a+b)/2`, `scale = max((b-a)/(2*logit(0.65)), 0.25)` and
   `e = clamp((z-center)/scale, -4, 4)`.
4. Give each segment weight `w = voiced samples / window samples`. Maintain
   `mean = sum(w*e)/sum(w)` for the whole call. Display
   `AI score = round(100*sigmoid(mean))`. Raw sigmoid model outputs are retained
   on the wire for compatibility, not displayed as probabilities.
5. The initial ordinary verdict needs two completed segments: score <=35 gives
   **Human**, >=65 gives **Likely AI**, otherwise **Inconclusive**. With continuous
   usable speech and fast inference, two segments are available around 8 seconds
   plus scheduling/inference latency. The third is available around 12 seconds.
   If fewer than two results have arrived by 15 seconds, display Inconclusive,
   retaining any one-segment score. Never force a human/AI label from no audio.
6. To change an established verdict, require two consecutive new segment updates
   whose cumulative scores support the same different label. Score updates remain
   live while the label awaits confirmation. This can temporarily leave a verdict
   beside a score crossing its usual threshold; the verdict is intentionally stable.
7. Separately inspect the most recent five eligible segments (normally about
   20 seconds of continuous audio; longer if windows were skipped). Show
   **Possible AI speech detected recently** when at least three are individually
   >=65 and their weighted recent score is >=65. Preserve the largest consecutive
   AI-like run as `max_ai_run` for evaluation, even after the recent warning clears.
   The recent warning does not relabel the entire call as AI.

These constants are conservative implementation defaults, NOT fitted validation
results. A single extreme segment has bounded influence, and more segments do
not automatically increase confidence. Strong systematic model errors can still
produce a wrong stable verdict. This layer cannot fix an inaccurate backbone.

Six seconds without speech clears only the rolling audio buffer, not the call
summary. An already-submitted valid segment may complete after the pause.
Inference generation IDs reject duplicated/retired completions. One inference
runs at a time. The existing 10-second pending-inference timeout remains.

## Contract and rollout

The additive envelope remains schema 1 on `scam-guard.risk`. New deepfake evidence
has `method: call-evidence-v1`, `state`, `score`, `score_kind: heuristic`, and
`recent_ai`, plus the prior finite/range-checked fields and `max_ai_run`. New iOS
clients validate the method and score fields as a unit, rejecting incomplete or
out-of-range evidence. Existing room/caller/agent identity checks, message ordering,
stream retirement and stub rejection remain. Transcript risk cannot supply a voice
verdict or score.

Old worker messages still decode through the legacy path; they have no new AI
score. Old apps can read the preserved legacy fields, but do not have the new
deadline UI or score display. Deploy the worker from **shrey** through the existing
LiveKit deployment workflow and build the iOS app from **shrey** together to test
the complete feature. A branch push alone does not deploy the worker.

Worker restarts start a fresh backend accumulator. The app retains the previous
assessment during warm-up, but this version does not restore backend evidence
from persistent storage across a worker crash. No raw caller audio is newly stored.

## Validation and remaining work

Run from the repository root:

```sh
python3 -m unittest discover -s 'backend/AI Deepfake Pipeline/LiveKit Setup' -p 'test_integration.py' -v
python3 -m unittest discover -s 'backend/AI Deepfake Pipeline/LiveKit Setup' -p 'test_cumulative.py' -v
```

The existing call-pipeline workflow includes the new cumulative regressions.
Tests cover early stable verdicts, conflicting segments, bounded outliers, late
synthetic switches, score recovery, silence retention, contiguous pauses,
clipping rejection and duplicate/retired inference completion. Generated JSON
fixtures exercise both legacy and cumulative Python-to-Swift wire decoding.

Foundation-only Swift checks can run without Xcode:

```sh
swiftc -module-cache-path /tmp/cac-swift-cache \
  ios/Callshield/Core/CallModels.swift \
  ios/Callshield/Production/PhoneModels.swift \
  ios/Callshield/Production/DeepfakeAssessment.swift \
  ios/Callshield/Production/PhoneSessionState.swift \
  ios/scripts/check_deepfake_contract.swift -o /tmp/cac-deepfake-contract
/tmp/cac-deepfake-contract ios/CallshieldTests/Fixtures/deepfake-wire.json
```

iOS XCTest regressions additionally cover 14.999 vs 15.000 seconds, incoming ring
time exclusion, late results, warm-up after the deadline, retained early scores,
invalid fields and history compatibility. The existing simulator CI builds the
real app and runs these tests. A physical call/model accuracy test is still needed.

Local validation in this editing environment: 25 backend/contract/transcript-state
tests pass. Foundation-only Swift compilation and all 11 wire fixtures, deadline,
late recovery, pause retention and history round-trip checks pass. Swift parsing
also checks the changed call UI, coordinator, LiveKit backend and XCTest source.
The transcript HTTP test cannot bind a local socket here. LiveKit SDK
orchestration tests and full iOS simulator tests require their normal CI runtime;
local Xcode is unavailable. Record CI results separately rather than treating
these environmental limits as passing tests.

Before describing any score as a probability, collect representative consented
phone-call examples, including mixed speech and long human-only calls. Separate
calls/speakers across fitting, calibration, threshold selection and final testing;
do not split prefixes of the same call across sets. Evaluate entire live replays:
calls ever falsely warned, detection delay, missed synthetic segments, verdict at
15 seconds, inconclusive frequency, and calibration across codecs and durations.
No learned call-level classifier/calibrator is included without those data.
