# Call Shield validation — October 17, 2026

Tested main commit `dca989c3126be4778638a002d3355a463f8789eb` in the separate attached checkout:
`/Users/keshavparikh/.codex/worktrees/callshield-oct17-testing/congressional-app-challenge-2026`.
The original working tree and its existing edits were preserved.

## Results

| Check | Result |
| --- | --- |
| Debug unit tests | 47 passed |
| Debug UI tests | 3 passed; all 3 passed again after the test correction |
| Release unit tests | 47 passed |
| Release UI tests | 2 passed, 1 intentionally skipped |
| Backend and tester tooling | 63 passed |
| Python syntax checks | Passed |
| Test patch whitespace | Passed |
| Normal Debug app build | Passed |
| App connection to deployed lobby | Connected; waiting for incoming calls |
| Actual incoming phone calls and model results | Not run |
| Physical iPhone background/lock screen and audio routing | Not run |

Environment: Xcode 26.6 (17F113), iOS Simulator 26.5, Apple Silicon Mac.
Dedicated clean simulator: Callshield Oct 17 Validation, iPhone 17 Pro,
`C914D5D9-4B89-4DF0-8009-B06094CC1E60`.

## Test correction

The first Release run hit two test assumptions. The analysis fixture is compiled only in Debug, so its UI test now explicitly skips Release. Another test expected an empty Favorites list on a simulator that already contained a saved favorite. Validation was repeated on a dedicated clean simulator without deleting existing app data. The Favorites check also waits up to three seconds for the view.

Only `ios/CallshieldUITests/ProductionUITests.swift` changed in the testing checkout. No app runtime code changed. The reviewable patch is [ui-test-fix.patch](ui-test-fix.patch). It has not been committed or pushed.

## Backend checks

| Suite | Passed |
| --- | ---: |
| Transcript pipeline | 9 |
| Worker integration | 15 |
| Tester access and probe tools | 12 |
| Ring lifecycle | 18 |
| Transcript model service | 2 |
| Node connector | 1 |
| Cloud contracts and probe checks | 6 |
| Total | 63 |

These cover event ordering, repeated calls, stale and invalid assessment results, pipeline failures, silence windows, cleanup, and limited tester configuration. Several suites use fake models or simulated services. Their success establishes control flow and service contracts, not real voice-classification or scam-detection accuracy.

Reproduction commands, from the test checkout with dependencies installed:

```text
cd "backend/AI Deepfake Pipeline/LiveKit Setup"
python -m unittest -v test_transcript_pipeline
python test_senior_ring.py

# From repository root:
python -m unittest discover -s "backend/AI Deepfake Pipeline/LiveKit Setup" -p "test*integration.py" -v
python -m unittest discover -s scripts -p "test_*.py" -v
python -m compileall -q backend scripts

cd "backend/Transcript-Based Detector"
python -m unittest -v test_model_service
node --test

# From repository root:
cd deploy/livekit
python -m unittest -v test_cloud test_probe_checks
```

All eight suite exit codes are recorded in the temporary summary at `/private/tmp/callshield-oct17-results/summary.json`.

For iOS, use the Callshield scheme and the dedicated simulator destination with a fresh derived-data path. Tests were run with `CALLSHIELD_DEMO=false`, `CALLSHIELD_LIVEKIT_HOST=`, and `CALLSHIELD_LOBBY_TOKEN=` overrides, so they could not connect as a live caller. The ordinary Run build used the limited tester configuration separately.

## Live test preparation and remaining work

The official tester artifact was retrieved, its SHA-256 verified, and the limited tester configuration installed only in the ignored local configuration of the test checkout. No credential is included in these deliverables. Tester access expires October 24, 2026 at 03:29 UTC (05:29 Berlin time).

The ordinary Run build launched and printed:
`[Callshield] lobby connected; waiting for incoming calls`.

This confirms that the app reaches the lobby. It does not confirm ringing, call media, either deployed model's output, or phone-call history.

Use [MACBOOK_TESTING.md](/Users/keshavparikh/.codex/worktrees/callshield-oct17-testing/congressional-app-challenge-2026/MACBOOK_TESTING.md) in the testing checkout for the official incoming-call instructions. Keep only one tester app using this identity open. A separate Android or other phone can call while the app runs on the Mac simulator; an owned iPhone is not required for that test.

| Live scenario | Status |
| --- | --- |
| Incoming ring, accept, and two-way audio | Not run |
| Human ordinary conversation | Not run |
| Synthetic ordinary speech | Not run |
| Synthetic scam scripts D1–D3 | Not run |
| Human scam script H1 | Not run |
| Bank-related benign control B2 | Not run |
| Eight-second silence and recovery | Not run |
| Mute/speaker and hang-up from both ends | Not run |
| Decline and another call without restarting | Not run |
| Saved call details and result freshness | Not run |
| Physical iPhone background/lock-screen/Bluetooth | Not run |

The six text fixtures are in [demo-pack.md](demo-pack.md) and the native demo pack. Audio files were not generated. Record actual results and false alarms; do not treat intended labels as measured results.

## Deliverables

- Three personal-style essay answers added to the existing shared essay document; original completed answers preserved.
- Four review comments on factual and technical claims.
- AI-use application response left for the team to complete from its actual work.
- Three fictional synthetic-voice scam scripts, one human scam script, and two benign controls.
- Five name ideas and prioritized future-feature proposals.
- Optional outreach draft, unsent.
- Native demo pack includes the verified test summary.

No sharing permissions were changed. No messages were sent and no application was submitted.
