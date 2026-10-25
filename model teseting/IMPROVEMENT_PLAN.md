# Trent improvement plan

Created October 22, 2026. Based on the completed [real-model evaluation](README.md), [regression report](regression_report.md), and verified updated source snapshots.

## Objective and evidence

Make Trent respond to the caller's current speech promptly, explain uncertainty clearly, handle quiet and degraded audio, and preserve useful call history without allowing it to suppress a new warning. Prove changes with held-out real recordings and live-path tests.

The evaluation supports a **mixed** conclusion, not a general accuracy claim:

| Finding | Implication for changes |
|---|---|
| Both versions identify the original AI clip around 8.02 s | Preserve this behavior; inference speed is not the main observed bottleneck. |
| New avoids AI headlines on both human controls, where old falsely warns | Keep bounded evidence and distinct-window accounting; a wholesale rollback would discard measured benefits. |
| New quiet variant submits zero windows | Fix eligibility before attempting to fix classification. |
| At 10 dB SNR, both aggregators miss AI on the new identical segments | Investigate window selection and model robustness separately from aggregation. |
| A 120 s repeated-human introduction keeps Human for 20.02 s of subsequent AI, including 8 s with an active warning | Remove whole-call history from the decision about current speech and fix conflicting presentation immediately. |
| New retains AI throughout 40 s of subsequent human speech | Recovery needs a bounded recent evidence horizon; retain historical AI separately. |
| Recent warning falsely activates for 8 s during a related human introduction | Promoting every recent warning straight to a confident AI verdict is not justified. |
| New retains evidence over long silence | Preserve history, but distinguish historical evidence from a fresh assessment. |
| Swift deadline is connection-based; audio processing begins after disclosure | Measure both clocks and explain missing results at the deadline. |

This is a planning document. Production detection code, thresholds, and weights have not been changed by this plan.

## Recommended design

Maintain three separate outputs with explicit time scopes:

1. **Current voice assessment:** recent, usable speech drives the prominent assessment. Older call evidence cannot delay a switch indefinitely.
2. **Whole-call evidence summary:** retain the bounded cumulative score for history/details, labeled as a heuristic summary of the call so far.
3. **Historical warning events:** retain when AI-like evidence was detected, its interval, and whether it is still current. A prior warning remains visible in history after current speech changes.

Also expose analysis availability and audio quality independently. Quiet audio, stale results, and insufficient speech should explain why a confident assessment is unavailable. They must not become Human evidence.

Keep raw logits as evidence. None of these scores should be called a calibrated probability. Voice classification and transcript/scam assessment remain separate; a human-like voice does not verify identity or make a call safe.

## Implementation sequence

### 1. P0 — Fix contradictory presentation and score meaning

**Change**

- Centralize assessment presentation in the Swift model/presentation layer so the call screen, accessibility output, and history use the same policy.
- When a fresh recent-AI warning is active, suppress a reassuring Human headline. Display a qualified warning such as “AI-like voice detected recently,” with the whole-call summary clearly secondary.
- The current contract lacks explicit model-evidence timestamps. Until those fields exist, suppress a reassuring Human headline when its warning flag is active and qualify the warning; do not infer evidence freshness from heartbeat receipt or the app’s updated-at time.
- Do not convert a recent warning automatically into a confident AI classification: the evaluation contains a recent-warning false alert.
- Label the existing cumulative value “Whole-call evidence,” rather than placing an unqualified “AI score” next to a headline describing current speech.
- Explain pending state changes when hysteresis leaves the headline unchanged after a score crosses a boundary. Prefer displaying a score from the same time scope as the current assessment once the backend supports it.
- Preserve prior results as dated historical results during silence or failure; do not imply they describe newly received speech.

**Likely files**

`ios/Callshield/Production/DeepfakeAssessment.swift`, `PhoneSessionState.swift`, `ProductionCallView.swift`, and history/detail views that consume the same assessment.

**Acceptance**

- No prominent Human headline or reassuring accessibility text coexists with an active, fresh recent-AI warning.
- Fixtures explicitly cover Human + warning, 65.6 + pending Inconclusive, no result, stale evidence, and recovery.
- Existing malformed-packet, stream-ordering, deadline, persistence, and late-recovery checks continue to pass.
- Replaying unchanged backend outputs changes presentation only; it does not masquerade as improved model accuracy.

This is the smallest useful first change and can be released independently of a new aggregation algorithm.

### 2. P0 — Make the benchmark support controlled development

**Change**

- Preserve the current README/results as an immutable dated baseline. Write each future run to a separate directory with source commit, configuration, checkpoint/config hashes, dependency lock, device, and seed.
- Parameterize the runner's audio paths, model folder, version directories, output directory, and device; validate actual decoded sample rates instead of relying on the supplied file's fixed rate.
- Add explicit configurations for windowing, eligibility, aggregation, and display policy. Avoid undocumented environment overrides.
- Run a two-by-two experiment: old/new window selection crossed with old/new aggregation, plus any proposed candidate. Use identical model outputs when isolating aggregation and real inference whenever preprocessing or submitted audio changes.
- Add stage metrics: speech eligibility, rejected-window reason, model submission, completion, publication, and displayed assessment. Retain exact submitted intervals and call-end cancellation semantics.
- Report initial detection, post-switch detection/recovery, time under an incorrect Human headline, warning duration, false warning events, abstention, and quality rejection separately.
- Extend automatic checks to enforce declared invariants and compare candidates with the frozen updated reference. A rejected or unscored sample must not disappear from metrics.

**Likely files**

New evaluation utilities under `model teseting/`; preserve the existing snapshots and result files. Production `test_offline.py` can share a tested replay utility later, with that refactor reviewed separately.

**Acceptance**

- A command reproduces the frozen results and generates a separate candidate report without overwriting the baseline.
- All 18 existing cases remain named regression cases. Prefixes, repeated clips, and transformations stay grouped by original source.
- Synthetic logic checks, real-model replays, and actual live-call results appear in separate report sections.
- The report never treats model windows as independent speakers or independent calls.

### 3. P1 — Replace the current headline's unlimited memory

**Change**

- Keep the bounded, speech-weighted cumulative engine as the whole-call summary.
- Add a separate current-speech engine with a finite recent horizon and explicit evidence timestamps. Compare a bounded recent-window mean with a time-decayed alternative on development data; select one before held-out testing.
- Candidate horizons such as 12–20 seconds are experiment settings, not validated defaults. Make recency and state-change hysteresis configurable and record them in each run.
- Retain bounded per-segment influence and minimum usable-evidence requirements. Evaluate asymmetric entry/recovery hysteresis, while measuring both missed AI and false warnings.
- Base evidence contribution on genuinely new usable audio. If overlapping model windows are explored for faster updates, account for their shared audio rather than counting each as an independent vote.
- Age out the *current* assessment and warning using timestamps. Silence does not accumulate Human evidence; historical warnings and whole-call statistics remain intact.
- Separate a transient current warning from “AI-like speech occurred earlier in this call.” Avoid one indefinite boolean representing both.

**Likely files**

`backend/AI Deepfake Pipeline/LiveKit Setup/risk.py`, `scoring.py`, `risk_protocol.py`; corresponding Swift decoding, assessment, session, and history models.

**Acceptance**

- With identical recent evidence and quality metadata, current assessment is unaffected by an arbitrarily long earlier human introduction once that introduction is outside the declared horizon.
- The same bounded-history property holds for AI→human recovery. Human still requires positive usable evidence; silence alone cannot cause recovery to Human.
- In the 120 s prefix regression, a fresh warning never leaves the prominent display Human. Detection and recovery delays are reported for every transition, including cases still Inconclusive at the end.
- Retain clean-AI detection and the standalone human controls as regression checks. Passing these reused samples is a development check, not independent validation.
- Choose operational delay and false-warning budgets before evaluating the held-out set. The report's single voice is insufficient to choose a defensible population operating point.

### 4. P1 — Fix quiet speech eligibility and expose quality failures

**Change**

- Instrument the present RMS gate: frame energy, estimated noise floor, speech decisions, eligible speech duration, clipping fraction, and rejection reason.
- Compare the fixed energy gate with a noise-adaptive gate and a speech detector suitable for quiet telephony speech. Evaluate candidates on quiet human speech, quiet AI speech, silence, hiss, music, and background conversation.
- Preserve contiguous four-second model inputs and natural pauses. Gate eligibility without removing pauses from the waveform by default.
- Treat gain normalization as a separate experiment. The model already normalizes submitted windows; normalization after submission cannot rescue audio rejected before submission. Amplifying noise before gating is not a sufficient solution.
- Keep quality rejection distinct from a Human/AI decision. Surface “Not enough usable speech,” “Audio too quiet,” “Audio distorted,” or “Analysis unavailable” as appropriate.
- Rename or document `voiced_sec` as an estimate until a validated speech detector supplies it.

**Likely files**

`audio_window.py`, `scoring.py`, agent quality/status payloads, `DeepfakeAssessment.swift`, and call-screen messaging.

**Acceptance**

- The existing −20 dB AI regression reaches real inference once sufficient genuine speech is available; measure whether model classification then succeeds rather than assuming it will.
- Quiet human speech also reaches inference. Silence and representative noise-only controls do not create confident voice verdicts simply because the gate became more permissive.
- Quality failures have explicit reasons and never silently count as successful analysis or Human evidence.
- Retain clipping safeguards and verify behavior on threshold boundaries, partial frames, pauses, and silence gaps.

### 5. P1 — Build an independent evaluation and calibration set

Start collection alongside steps 1–4; it is a dependency for choosing thresholds or shipping classification-policy changes.

**Data plan**

- Expand beyond the two male audiobook readers: diverse voices, ages, accents, languages, microphones, quiet speakers, and conversational speech relevant to Callma's users.
- Include multiple independently generated synthetic voices, engines, cloning methods, scripts, and recording sessions. Include difficult human speech rather than only clean controls.
- Collect consented real phone-path recordings and label source provenance. Include natural human→AI/AI→human transitions as well as constructed stress tests.
- Add measured telephony-band filtering, G.711 μ-law/A-law, relevant deployed codecs, packet loss, echo, gain control, background talk, and realistic nonstationary noise as separate conditions.
- Record licensing/consent, provenance, source identity, transformation lineage, and any known overlap with model training data. The existing LibriSpeech controls have unknown training overlap.
- Keep all derivatives of a source in one partition. Separate development, calibration, and final testing by human speaker/source session and synthetic voice/system where feasible; reserve systems for generalization tests.
- An initial collection milestone could be at least 30 human speakers and 10 synthetic voice identities across at least 3 systems. These are coverage goals, **not** a statistically sufficient release benchmark. Set final sample size from the chosen false-warning and missed-detection budgets.

**Metrics and selection**

- Primary: independent human calls ever falsely warned, AI calls missed, verdict/warning by the declared deadline, time to detect a switch, recovery time, incorrect-Human duration, abstention and analysis coverage.
- Distinguish headline false alerts from recent-warning false alerts; report persistence, not only first occurrence.
- Present per-condition and per-source results with uncertainty based on independent calls/speakers, accounting for related transformations. Report unknown/missing outcomes.
- Select gating, horizon, and operating thresholds on development/calibration data only. Freeze the choice before final testing. Keep the current report's post-hoc diagnostics labeled as development stress cases.
- Explore probability calibration only if the data and evaluation support it. Otherwise keep all mapped scores explicitly heuristic.

**Acceptance**

A versioned data manifest and preregistered metric/release specification exist before candidate selection. Final held-out results report sample counts and uncertainty, including any inconclusive outcomes or unmet release budgets.

### 6. P2 — Improve degraded-audio model behavior when the evidence supports it

**Change**

- Use the factorial experiment to identify whether 10 dB misses arise from pause preservation, speech/noise selection, model input distribution, aggregation, or several together.
- Compare supported four-second input policies without changing the original checkpoint during this experiment. Any alternative representation gets its own label and held-out evaluation.
- If the same degraded windows remain poorly separated, investigate phone-domain augmentation or fine-tuning with verified human and AI data: codec effects, level changes, realistic noise, clipping, reverberation, and genuine pauses.
- Preserve the training recipe, split manifest, random seeds, checkpoints and learning curves. Evaluate clean-speech regressions and unseen synthetic systems, not only the noisy ElevenLabs clip.
- Recalibrate thresholds only on a separate calibration partition after model/preprocessing selection. Version weights, architecture, preprocessing, aggregation and thresholds together.

**Acceptance**

A candidate meets the predefined missed-detection, false-warning, abstention and latency budgets on held-out phone-domain data, with per-condition evidence. A recovered single noisy clip is insufficient. Do not lower a cutoff solely to turn this report's final 63.3 into AI.

### 7. P1/P2 — Make deadlines, freshness, and the live path observable

**Change**

- Record connection, notice start/end, first caller audio, sufficient speech, submission, completion, publication, app receipt and display events, correlated by call/stream/window identifiers.
- Use local monotonic durations within each process; measure cross-device timing with an explicit clock-alignment method rather than subtracting unrelated monotonic clocks.
- Preserve the connection-based 15-second initial display deadline. At expiry, distinguish insufficient usable speech, disclosure still pending, unavailable inference, and mixed evidence where the contract can establish the reason.
- Keep disclosure-before-analysis gating. Do not process caller audio early to make benchmark timing appear better.
- Preserve one-inference-at-a-time behavior and explicit timeout/generation handling. Test delayed and out-of-order results, interrupted calls, heartbeat loss, agent restarts and late recovery.
- Prewarm and health-check the model before accepting scoring work. Pin the official architecture config locally and validate checkpoint/config hashes at startup.
- Benchmark the actual deployment device, concurrency and cold/warm startup. Local MPS's ~20 ms inference is not a cloud or end-to-end service guarantee.
- Add metadata-only operational counters by default. Keep sensitive audio/transcripts out of routine logs; retain evaluation recordings only under the explicit data policy.

**Acceptance**

- Python/Swift fixture tests cover each new state and field. End-to-end tests verify the deadline against an actual connected-call clock, including notice delay/failure.
- Complete the outstanding iOS XCTest/simulator checks and consented physical-device LiveKit/phone-call tests; save actual packet/display timing.
- Publish p50/p95 end-to-end delay, coverage and failure counts separately from model computation, plus results under concurrent calls.

### 8. P2 — Ship with a compatible contract and measurable rollback

**Change**

- Specify new fields such as `current_state`, `current_score`, `whole_call_score`, evidence interval, freshness, quality/status reason and historical warning events before implementation. Final names belong to the contract review.
- The existing Swift decoder accepts only `call-evidence-v1`; a new method identifier alone will cause rejection. Add explicit decoder support and legacy fixtures, then use capability negotiation or version-targeted messages during migration. Do not silently reinterpret v1's score.
- Roll out the presentation fix first, followed by separately flagged eligibility and current-evidence changes. A model/checkpoint update is a separate release.
- Run candidate and reference in shadow evaluation without duplicate user alerts. Track disagreements and review independently labeled outcomes.
- Stage deployment only after meeting the frozen release criteria. Retain an operational fallback that includes the contradiction fix; rolling back aggregation should not restore reassuring Human + active warning presentation.
- Archive source/config hashes and a release benchmark for each stage.

**Acceptance**

Old supported clients decode their intended contract, new clients handle both supported versions, rollback is exercised, and candidate adoption is tied to independent evidence rather than the development examples.

## Suggested pull-request breakdown

| PR | Deliverable | Depends on |
|---|---|---|
| 1 | Consistent current-warning presentation, explicit whole-call score labels, Swift fixtures | Existing verified updated revision |
| 2 | Versioned benchmark runner, factorial comparisons, frozen outputs and explicit quality/coverage metrics | Existing evaluation artifacts |
| 3 | Versioned evidence/freshness contract and compatible Swift/backend support | PR 1; contract design |
| 4 | Finite-horizon current-speech engine, historical event retention and transition tests | PR 2, PR 3 |
| 5 | Quiet-speech eligibility candidate, quality reasons and noise-only controls | PR 2, PR 3; development data |
| 6 | Independent data manifest, calibration protocol and held-out benchmark report | Collection starts immediately; evaluates PR 4/5 |
| 7 | Live-path timing instrumentation, device/XCTest checks, deployment load tests | PR 3; can proceed alongside PR 4/5 |
| 8 | Optional model/preprocessing update with separate calibration and held-out validation | PR 6 shows remaining model weakness |
| 9 | Shadow comparison, staged deployment and rollback exercise | Release gates satisfied for each enabled change |

The first implementation priority is PR 1, followed by PR 2 and the contract design. Begin independent data collection in parallel. Actual model changes come after attribution experiments and data coverage; current evidence does not justify replacing the detector or claiming that any untested candidate improves general accuracy.

## Definition of completion

- Prominent assessment and warnings communicate the same time scope; history is separately labeled.
- Quiet speech reaches analysis when usable, while poor quality and insufficient evidence remain explicit.
- Current assessment has a bounded dependence on past speech and recovers in both transition directions.
- Human false alerts, AI misses, abstention, detection/recovery and deadline behavior meet predeclared budgets on independent data.
- Unit, mocked integration, Python/Swift contract, simulator and actual phone-path checks have clear outcomes; no unexecuted check is described as passing.
- Reproducible artifacts identify exactly what changed and support an operational rollback.

## Working-copy note

The benchmark's updated reference is `ec2f4dd80de433f176b1d9f90a20ca35d60707aa`. The preserved local checkout was `improved-ui` at `0fe9400e702abb62a2e7e9df5bd6dfd5a3cdef51`. Before implementation, inspect current status and obtain a safe branch containing the cumulative feature and the user's current work; do not patch frozen snapshots or blindly replace the working checkout with the benchmark revision.
