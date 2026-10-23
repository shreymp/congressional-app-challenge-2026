# Regression checks

These checks exercise software behavior with controlled evidence and shared wire fixtures. They are separate from the real-model audio benchmark in README.md and do not establish detector accuracy.

| Check | Baseline | Updated |
|---|---:|---:|
| `test_integration.py` | 9 passed | 9 passed |
| `test_cumulative.py` | Not present | 8 passed |
| `test_offline.py` CLI, seeded stub detector | Passed | Passed |
| `test_agent_integration.py`, mocked rooms/audio | 6 passed | 10 passed |
| `test_recording_notice.py`, synthetic WAV/fake transport | Not present | 6 passed |
| Foundation Python-to-Swift wire fixtures | 8 passed | 11 passed |
| Swift 15-second boundary, late recovery, pause retention, history round-trip | Not implemented | Passed |

Python logs are `logs/fallback_*`; exact subprocess commands, stdout/stderr and exit codes are recorded there. Snapshot test imports override only `test_integration.FIXTURE` to the corresponding saved fixture path because the evaluation snapshots have a flattened layout. This is a harness path correction; production code is unchanged. The offline CLI smoke tests use `DETECTOR=stub` and seeded random output to test plumbing only; those scores are excluded from every real-audio result.

The Swift checks compile the verified snapshot sources with Apple Swift 6.4, target arm64-apple-macosx26.0 (Xcode 27.1). They require Foundation and no phone call or network. `logs/swift_*.txt` and `results/swift_checks.json` contain commands and results. The baseline and updated shared-fixture checks also reject malformed and oversized payloads. The updated original repository checker asserts that the initial state remains Analyzing at 14.999 seconds and becomes Inconclusive at 15 seconds, that subsequent human evidence recovers, that a waiting heartbeat preserves an established result, and that saved history round-trips.

Reproduce Swift checks from the project root:

```sh
sh "model teseting/run_swift_checks.sh"
```

Equivalent Python entry point:

```sh
.venv/bin/python "model teseting/run_swift_checks.py"
```

Reproduce mocked-agent and notice checks (45-second timeout per suite, no service connections):

```sh
.venv/bin/python "model teseting/run_agent_checks.py"
```

These passed with LiveKit 1.1.20, livekit-agents 1.8.6, livekit-api 1.2.1 and python-dotenv 1.2.4 installed. `logs/baseline_test_agent_integration.txt`, `logs/current_test_agent_integration.txt`, `logs/current_test_recording_notice.txt` and `results/agent_checks.json` contain exact commands and outputs. Tests use fake detectors, rooms/audio and notice transports; no actual model inference, phone call or LiveKit service connection is made. Recording-notice tests create temporary synthetic assets rather than requiring the production spoken notice asset.

## Timing and app interpretation

The production `agent.py` initializes `next_score` to monotonic call time + `SCORE_EVERY_SEC` (default 1 second). For each audio frame it pushes PCM, then attempts a score only when the timer has elapsed and no previous score task is active. It advances the timer before requesting the snapshot, even if that snapshot is not eligible. There is one in-flight model task. On model completion, it calls `session.refresh(completion_time)` before `complete(...)` and publishes at completion time. A two-second heartbeat can publish intermediate status. Stream shutdown cancels the in-flight score task; there is no mandatory end-of-file result flush in the production agent.

The updated production agent awaits recording-notice playback before starting its scoring timer and opening the caller-audio stream (15-second notice timeout). The audio replay measures from supplied caller-audio time and excludes this notice phase. Consequently the app's `connectedAt + 15 seconds` deadline and a replay's 15-second audio milestone are different clocks. Notice failure publishes unavailable and disables voice/transcript processing for that call.

Updated Swift consumes `call-evidence-v1` evidence by copying `e.state` to the main assessment and copying `e.score` and `e.recent_ai` separately. Thus the recent warning is not the main verdict. Legacy evidence uses high + at least 3 updates → AI; elevated → uncertain; listening + at least 3 human steps → human; otherwise analyzing.

The updated iOS coordinator schedules a task at `connectedAt + 15 seconds`. The session converts waiting/analyzing to uncertain (display title Inconclusive); it does not fabricate a completed detector classification. Existing human, AI, uncertain, or unavailable results are not converted into a new model verdict by this deadline. Late evidence can replace the deadline result. Waiting/analyzing heartbeats cannot erase an established human/AI/uncertain result with at least two evidence windows. These are tested state-machine semantics; end-to-end timer scheduling, packet transport, rendering and physical-call latency remain unmeasured.

## Unexecuted platform checks

Full iOS XCTest, simulator rendering and live LiveKit/phone-call checks were not executed. The first sandboxed `xcrun simctl list devices available` probe failed to connect to CoreSimulatorService and could not write its normal user-library log. A requested outside-sandbox probe was aborted while awaiting approval; it produced no simulator inventory. This does not establish that simulators are absent or that Xcode tests would fail. The bounded Foundation checks above succeeded without this access.

Other orchestration suites such as `test_senior_ring.py` were not executed as part of these bounded regression checks. No production detection logic was modified.
