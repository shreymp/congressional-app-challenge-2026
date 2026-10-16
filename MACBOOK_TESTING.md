# Callshield: MacBook simulator test handoff

Use this branch's complete code, including the simulator call changes. The app
is `ios/Callshield.xcodeproj`, scheme **Callshield**, not ScamTranscript.
Xcode 26 and Python 3.11+ are required. Xcode must include an iOS Simulator
runtime (Xcode Settings → Components). No Apple Developer team or paid account
is needed for the simulator build. Commands below run from the repository root.

## 1. Get the code and install the test tools

```sh
git clone https://github.com/shreymp/congressional-app-challenge-2026.git
cd congressional-app-challenge-2026
git switch codex/livekit-transcript-pipeline
git pull --ff-only
python3 scripts/mac_call_test.py setup
```

For an existing checkout, commit/stash your own work before switching branches.
If the branch has since been merged, use updated `main` instead. The setup script
creates `.venv-calltest`; subsequent commands automatically use that environment.
If `python3 --version` is below 3.11, install a newer Python and use that executable.
If Xcode tools point at Command Line Tools, select the installed full Xcode in
Xcode Settings → Locations → Command Line Tools.

## 2. Configure access locally

The project owner supplies the **actual LiveKit WebSocket URL/host** and either:

- A short-lived lobby token for identity `senior`, room `senior-lobby`, from
  `tools/mint_lobby_token.py --days 1`. Then run:

  ```sh
  python3 scripts/mac_call_test.py configure
  ```

- Existing project backend credentials when the friend will also run ring tests,
  risk monitoring or local inference. Enter them privately at the prompts:

  ```sh
  python3 scripts/mac_call_test.py configure --backend --days 1
  ```

These commands save `ios/Configuration/Local.xcconfig`; backend mode also saves
`backend/AI Deepfake Pipeline/LiveKit Setup/.env.local`. Both are ignored by Git,
written with owner-only permissions, and must remain private. API secrets never
go into the app. The lobby token is embedded in the built app, expires, and gives
access to incoming call invites: do not distribute that build. Reconfigure and
rebuild to renew it. Configuring preserves existing signing/team settings.

Use the same lobby room/identity as the deployed worker. If the deployment uses
overrides, match `SENIOR_LOBBY_ROOM` and `SENIOR_IDENTITY` in `.env.local` before
minting. Only **one** app may connect as `senior`: close the other simulator or
phone app first, because the second connection disconnects the first.

## 3. Build and open the simulator

```sh
python3 scripts/mac_call_test.py doctor
xcrun simctl list devices available
```

Copy an available iPhone simulator's UUID. Boot it in Simulator, or run
`xcrun simctl boot UUID` if it is shut down. Replace `UUID` below with that value:

```sh
python3 scripts/mac_call_test.py simulator --device UUID
```

Alternatively open `ios/Callshield.xcodeproj`, select **Callshield** and an iPhone
simulator, and choose Product → Run. Use Run for live calls: Product → Test
deliberately disables the real calling backend. Keep `CALLSHIELD_DEMO=false`.
Allow microphone access in the app and in macOS if prompted; select the Mac's
microphone in Simulator's audio-input settings. Use headphones to prevent feedback.
Keep the app visible and awake. Xcode's console should report a lobby connection.

Simulator builds use the app's **Accept / Decline / End call / mute** controls,
because CallKit cannot provide the system incoming-call/audio flow in Simulator.
The screen says **Simulator call test**. The network, LiveKit media, caller audio,
and detector updates are real; this does not simulate risk scores. Physical iPhones
continue to use CallKit. Cellular outgoing calls, native lock-screen calling,
PushKit, Bluetooth routing and physical-device audio need a separate iPhone test.

## 4. Test ringing/audio first (no phone number required)

This requires backend credentials on the Mac. In a second Terminal:

```sh
python3 scripts/mac_call_test.py doctor --backend
python3 scripts/mac_call_test.py ring
```

The tool creates a temporary `ringtest-...` room and sends the same invite used by
incoming phone calls. Accept in the simulator: hear quiet beeps and speak into the
Mac microphone. The Terminal should report `senior answered` and moving microphone
levels. End in the app; the room should close. Run it again, then press Ctrl+C in
Terminal: the app should end the call. Also try Decline and leaving it unanswered.

**This ring test does not dispatch the detector and does not test transcription.**
Beep audio is not suitable speech for either model. A lobby-token-only tester can
have the project owner run the ring command from their configured backend instead.

## 5. Test the deployed worker and both detection branches

With the app still open, call **+1 267-509-1164** from a separate real phone.
Carrier forwarding is unnecessary for this direct test. Accept in the simulator
and speak naturally from the calling phone for at least 15–20 seconds. Test only
with people who know they are participating. Audio recording defaults to off.

With backend credentials, run:

```sh
python3 scripts/mac_call_test.py watch
```

The watcher joins the newest `call-` room; if several exist, use the exact room:
`python3 scripts/mac_call_test.py watch call-EXACT-NAME`. On LiveKit Cloud, check
Telephony → Calls and the associated session for the agent job and its actual
version. The dispatch name must be `scam-guard`, deployment `production`.

Pass conditions:

| Check | Expected result |
| --- | --- |
| Incoming call | One `call-...` room and one intended `scam-guard` worker; app shows Accept |
| Answer | Caller and simulator hear each other; duration starts after media activates |
| Deepfake | Watcher shows `model=real`, advancing sequence and scored windows; app moves from waiting/analyzing to a result or uncertainty |
| Transcript | Watcher shows `transcript=monitoring`, finite probability and advancing scored revisions after speech |
| Silence | Old voice verdict stops being current; no repeated scoring of an unchanged silent window |
| Hang up | Test caller hangs up → app ends; app hangs up → caller disconnects after the existing grace period |
| Repeat | A second call works without restarting the app; previous-call risk cannot appear |

The iOS UI currently displays the **voice/deepfake** assessment. Inspect the
transcript probability in the watcher; a voice label alone does not prove JEV is
running. Model accuracy and thresholds are separate from this plumbing check.
`stub` scores, null transcript probability, `stt_unavailable`, `jev_unavailable`
or expired scores do **not** count as a full-model pass.

## Optional: run the models on the MacBook

Skip this section when the deployed worker already has both models and reachable
transcript services. Starting local services alone cannot fix a cloud worker's
`127.0.0.1` URL: that address refers to its own container, not the Mac.

For a local full-pipeline test, first stop the old hosted worker or otherwise make
sure it cannot receive the same `scam-guard` jobs. Do not run two eligible workers
and assume the Mac gets the call. The local path requires Node 22+ and team access
to the private JEV release files. Configure Git HTTPS credentials, or set
`GITHUB_TOKEN`/`GH_TOKEN` privately with repository read access.

```sh
python3 scripts/mac_call_test.py setup --local
python3 scripts/mac_call_test.py models --deepfake-weights /absolute/path/to/best.pt
python3 scripts/mac_call_test.py services --agent
```

The model command downloads checksum-verified Vosk and published JEV bundles;
copy the team's actual trained `best.pt` from its owner. That large model is
excluded from Git and has no download URL in this repo; the script cannot invent
or replace it. `inference.py` and `detector_config.json` are already checked in.
The pretrained deepfake backbone configuration may also download on first load.

The services command supervises the Python ONNX service, Node connector and local
agent, checks actual JEV inference before starting the agent, and stops its child
processes on Ctrl+C. It refuses occupied ports 8000/3000. Another Terminal:

```sh
python3 scripts/mac_call_test.py doctor --backend --local
python3 scripts/mac_call_test.py watch
```

`doctor --local` loads and warms the real deepfake model, loads Vosk, and makes a
real request through the model/connector. It may take a while on first run.
`services` without `--agent` starts just the two local transcript services.
Hosted deployments must package/reach their own model files and services; none
of the local setup commands uploads weights or redeploys the cloud agent.

## Troubleshooting and test record

- No ring: check production mode, host/token expiry, app in foreground, only one
  `senior`, matching lobby settings, and dispatch/session errors.
- Ring test works but phone call does not: inspect the deployed worker's startup
  logs and job version; the ring tool bypasses the worker entirely.
- No audio: check Simulator audio input and macOS microphone permission, then
  quit/relaunch after changing permission. A physical iPhone is the reference for
  native audio behavior; simulator hardware/OS combinations can still differ.
- Voice unavailable: inspect model load errors, `best.pt`, `model` mode, risk schema
  and worker version. Transcript unavailable: check Vosk path, JEV health and an
  actual POST through the connector. `modelConfigured` alone is insufficient.
- Import/SDK build error: resolve Swift packages in Xcode and verify Xcode 26.
  The app uses LiveKit Swift 2.17.0; Debug builds select only the active simulator architecture to match its package build. Do not regenerate the project to fix signing;
  put personal settings in `Local.xcconfig`.
- No answer: voicemail/family notification is still a stub. Background ringing
  and outgoing phone detection are not implemented by this test setup.

Record commit SHA (`git rev-parse HEAD`), Mac/Xcode/iOS runtime versions, deployed
agent version, each pass/fail above and sanitized error messages. Do not attach
API keys, lobby/call tokens, `.env.local`, `Local.xcconfig`, or private recordings.

Automated local checks:

```sh
python3 -m unittest discover -s scripts -p 'test_*.py' -v
# With the full backend environment active:
.venv-calltest/bin/python -m unittest discover -s 'backend/AI Deepfake Pipeline/LiveKit Setup' -p 'test*integration.py' -v
.venv-calltest/bin/python -m unittest discover -s 'backend/AI Deepfake Pipeline/LiveKit Setup' -p 'test_transcript_pipeline.py' -v
cd 'backend/Transcript-Based Detector'
../../.venv-calltest/bin/python -m unittest -v test_model_service
node --test
```

The Mac simulator CI compiles/tests the app without credentials. Real LiveKit,
PSTN calls and model accuracy still require the manual checks above.

References: [LiveKit Swift SDK](https://github.com/livekit/client-sdk-swift),
[CallKit simulator limitation](https://github.com/livekit-examples/flutter-callkit),
[LiveKit dispatch rules](https://docs.livekit.io/telephony/accepting-calls/dispatch-rule/).
