# Callshield backend fixes — October 19, 2026

The local backend now closes declined and unanswered calls instead of only logging them and leaving the caller ringing. Production has not been deployed or retested with this patch. The earlier live-call report remains historical evidence and is unchanged.

Base commit: `dca989c3126be4778638a002d3355a463f8789eb` on `main`, plus the uncommitted patch in this directory. Source fingerprints are in `validation-final.json`.

## Changes

- An observed decline (the app leaves without publishing its microphone) closes the call room after the existing 5-second reconnection grace period. This disconnects the telephone caller.
- An unanswered call closes at the configured ring window, normally 30 seconds, including when the app is offline or token/invitation delivery fails.
- The optional no-answer hook still runs exactly once. A hook exception cannot prevent room cleanup. Voicemail and family notifications remain unimplemented.
- Once a no-answer decision starts cleanup, a late join or microphone publication cannot revive the call or stop its deletion retries.
- Room deletion retains the existing limit of three attempts and five seconds per API request. Swallowed errors and stalled requests are covered. If the caller remains connected after the retries, the supervisor returns `cleanup_failed` instead of falsely returning successful hang-up. Successful no-answer cleanup returns `unanswered`.
- Brief disconnections within the grace period still permit reconnection. Answered calls remain active past the ringing window. Caller hang-up and normal answered-call hang-up retain their existing behavior.
- Updated the backend setup and behavior documentation. No iOS or model code was changed.

Changed source files: `senior_ring.py`, `test_senior_ring.py`, `README.md`, and `INCOMING_CALL_SETUP.md`, all under `backend/AI Deepfake Pipeline/LiveKit Setup/`.

## Verification and execution history

| Check | Result | Evidence |
| --- | --- | --- |
| New behavior checks against the original runtime | 13 passed, 6 failed; failures reproduced missing disconnects and cleanup reporting | `logs/ring-before-fix.log` |
| Initial fix | 19 passed, 0 failed | `logs/ring-after-fix.log` |
| Expanded backend run | All non-ring suites passed; ring suite 19 passed, 1 failed from a new test deadline mismatch | `logs/backend-summary.json`, individual suite logs |
| Final ring suite after correcting the test timing | 20 passed, 0 failed | `logs/ring-lifecycle-final.log` |
| Final aggregate | **65 passed, 0 failed** across seven suites | `validation-final.json` |

The new job-wiring test inherited a 5-second ringing window while its wait helper allowed only 3 seconds. It was corrected to use the suite's accelerated 0.6-second ringing window. The final ring rerun passed; the six unchanged suites did not need rerunning. Earlier failed logs are retained.

Final suite counts: transcript pipeline 9; worker integration 15; tester tools 12; call lifecycle 20; transcript model service 2; Node connector 1; cloud/probe contracts 6. Tests use fake services/models where appropriate and verify backend behavior and contracts. They do not establish production deployment or model accuracy. The job-wiring test exercises the real framework's shutdown registration with a fake room/API context.

The backend runner and all logs are included. Python checks used the existing isolated test environment. Reproduce with dependencies installed:

```sh
CALLSHIELD_TEST_PYTHON=/private/tmp/callshield-oct17-venv/bin/python python3 docs/testing/2026-10-19-fixes/run-backend-checks.py
```

The checked-in CI backend workflow already runs the changed call lifecycle suite. Whitespace validation also passed. Earlier iOS test results belong to the original testing report; iOS tests were not rerun for this backend-only change.

## Remaining boundaries and deployment

An early decline before the app ever joins is not observable through the current receive-only invitation protocol. It is closed at the ring timeout, rather than after five seconds. This fix does not claim immediate rejection for that case. An actual LiveKit deletion outage can still leave the caller connected; it now receives an explicit failure result and error log.

The original extra missed invitation needs server-side correlation before attributing a cause. No speculative model or invitation protocol change was made. Microphone permission was already resolved during setup. Mac volume, browser audio-meter behavior, independent two-way listening, and the full 45–60-second human conversation remain testing/setup matters.

The tester configuration grants app access; it is not a deployment credential. Deploy the reviewed patch through the repository's existing LiveKit real-model workflow using the project owner's authorized deployment environment, following `deploy/livekit/README.md`. No GitHub push, production deployment, or new live call was performed in this fix turn.

After deployment, confirm the deployed version, run the existing backend audio probe, then make fresh telephone calls to check: decline after the app joins (remote end disconnects after the grace period), unanswered/offline app (remote end disconnects at the ring timeout), answer and hang up from both ends, and another call without a restart. Capture both endpoint states and service logs; the audio probe alone does not test the SIP decline path.

`backend-fix.patch` contains the four-file source/documentation change for review or transfer. No connection JSON, local configuration, or production credential is included.
