# Full app test on a MacBook simulator

The tester does **not** need a LiveKit account, API key, API secret, model files,
Node, PyTorch, or a running backend on the Mac. The hosted worker runs both
AI voice/deepfake detection and Vosk → JEV transcript analysis.

Use **main**, `ios/Callshield.xcodeproj`, scheme **Callshield**, Xcode 26 and an
installed iOS Simulator runtime. The separate ScamTranscript app is not this
full calling app. No paid Apple account is needed for simulator builds.

## 1. Pull the app and install its connection settings

```sh
git clone https://github.com/shreymp/congressional-app-challenge-2026.git
cd congressional-app-challenge-2026
git switch main
git pull --ff-only
python3 scripts/tester_access.py install
open ios/Callshield.xcodeproj
```

The install command uses GitHub CLI (`gh`) and the same GitHub account that can
read this **private repository and its Actions artifacts**. If needed, install
GitHub CLI from https://cli.github.com and run `gh auth login` once.
It downloads the latest **Tester app access** configuration and writes the
ignored `ios/Configuration/Local.xcconfig`. It preserves personal signing settings.
No LiveKit credentials are requested or copied to the Mac.

Without GitHub CLI: open repository **Actions → Tester app access → latest
successful main run**, download the **callshield-tester-access** artifact, unzip
it, then run:

```sh
python3 scripts/tester_access.py install --config /absolute/path/CallshieldTester.json
```

GitHub's stored server secrets sign a limited, seven-day app token. Only this
room-scoped token and the project host go into the app; the API key and secret
stay in Actions/cloud. Keep the downloaded JSON, Local.xcconfig and resulting
build private. The app receives short-lived tokens for individual calls from
the worker. Do not commit configuration/token files.

If access has expired, the owner runs **Tester app access** on **main** in Actions;
then repeat install and rebuild. Only one simulator/phone may use this test
identity at a time: close other Callshield instances before testing.

## 2. Run the simulator app

Select **Callshield** and an available iPhone simulator, then **Product → Run**.
Resolve Swift packages if Xcode asks. Use Xcode 26 and select the full Xcode in
Settings → Locations → Command Line Tools. Product → Test deliberately disables
live network calling; it is not how to receive the real test call.

Allow microphone access in iOS and macOS. Select the Mac microphone in Simulator's
audio-input settings. Wear headphones to prevent call feedback. Keep the app open
and awake. Xcode's console should report **lobby connected; waiting for incoming
calls**. The app uses its own Accept/Decline/mute/End controls in Simulator.

## 3. Call the number and check both results on screen

From a separate real phone, call **+1 267-509-1164**. No forwarding setup is needed.
Accept in the simulator and confirm two-way audio. Speak from the **calling phone**
for at least **45–60 seconds**; both pipelines analyze only that caller's audio.
Talking into the Mac tests the return audio path, not the caller detectors.

The connected call screen has two separate cards:

| Card | What the tester should see |
| --- | --- |
| Caller’s voice | Analyzing → a human, possible AI, or uncertain result; missing service updates show unavailable |
| Scam warning | Listening → a scam-language result and **Highest scam risk this call: …%**; the peak cannot decrease during the call |

The scam card shows analysis of the caller's words, without a live transcript.
Saved excerpts are off by default; see [the controlled-test option](docs/meeting-2026-10-20/STATUS.md) before enabling them. A high transcript score must not change a human voice into
an AI voice label. Model/service failures appear as unavailable, and expired
transcript results stop being shown as current.

Test these scenarios with consenting participants:

1. **Ordinary human speech:** a natural conversation for 45–60 seconds. Require
   current feedback from both cards; record the actual scores/labels.
2. **Scam-like language:** read a test script about urgently sending money or
   sharing a bank verification code. Watch the highest scam-risk score.
   Use fictional details only.
3. **AI voice:** play a known synthesized speech sample into the calling phone
   for 45–60 seconds. Record the voice label and transcript feedback. Audio played
   through a phone speaker/microphone is a different domain from clean model audio;
   a wrong label is a model-quality finding, not proof that inference never ran.
4. **Pause:** stop caller speech for at least 8 seconds. The current analysis
   should wait for more speech while the previous result remains visible. Service outages must still be shown.
5. **Call controls:** mute/unmute, speaker, decline and hang-up from each end.
6. **Repeat:** call again without restarting the app. Previous-call scores must
   not appear in the new call. After hang-up, call details preserve each pipeline's
   last available assessment as historical evidence.

Record the commit (`git rev-parse HEAD`), Mac/Xcode/iOS runtime, scenario,
both on-screen results, audio/control behavior and sanitized errors. Do not
share keys, connection tokens, Local.xcconfig or private recordings.

A finite score or a successfully connected call proves plumbing, not calibrated
model accuracy. This test does not implement automatic blocking, voicemail/family
notifications, background PushKit ringing, or detection of outgoing cellular calls.
Physical iPhone CallKit, lock-screen ringing and device audio require later tests.

## Troubleshooting

- No ring: use Run, not Test; check app access expiry, production mode, microphone
  permission, only one `senior` app, and Xcode's lobby connection/error log.
- No sound: check Simulator audio input/output and macOS permission; relaunch after
  permission changes. Confirm phone volume and that neither end is muted.
- Transcript unavailable/stale: wait for caller speech. If it persists, send the
  sanitized status and call timestamp to the owner for worker/STT/JEV diagnostics.
- One pipeline has a result: inspect the other card separately; a voice label does
  not prove transcript scoring is running.
- Expired/missing tester artifact: owner renews **Tester app access**, then tester
  repeats install and rebuilds. No LiveKit login is required.

## Owner-only diagnostics (not required for the tester's phone-call test)

The owner can run **LiveKit real models** with `probe_only=true` in GitHub Actions
to send fixture speech through the deployed worker without using the app. It
requires 35 seconds of fresh evidence and advancing results from both pipelines.
The **Callshield simulator** workflow builds and tests the app without credentials.

For local diagnostic tools only:

```sh
python3 scripts/mac_call_test.py setup
python3 scripts/mac_call_test.py configure --backend
python3 scripts/mac_call_test.py cloud-probe
python3 scripts/mac_call_test.py full-call
python3 scripts/mac_call_test.py watch
```

`full-call` rings a connected tester app with synthetic fixture speech and checks
both cloud pipelines plus returning Mac microphone audio. `watch` observes an
active telephone room. Those tools create/inspect server resources and therefore
use owner API credentials; normal incoming calls and on-screen feedback do not.
Do not start a local `scam-guard` worker alongside production.
