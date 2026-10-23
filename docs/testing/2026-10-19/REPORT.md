# Callshield test report — October 19, 2026

The deployed phone-call route produced separate, advancing voice and transcript results in two controlled synthetic-speech calls placed through Google Voice. Silence recovery, repeated-call score reset, saved assessments, and call controls were exercised. Declining a call dismisses it in the app but leaves the caller ringing. The complete requested human-conversation and independently verified two-way-audio checks remain open.

## Version and environment

- Tested `main`, commit `dca989c3126be4778638a002d3355a463f8789eb`, fetched and fast-forwarded before testing. No app or backend runtime source was changed, committed, or pushed.
- Xcode 26.6, build 17F113; macOS 26.5.2; Apple Silicon; iOS Simulator 26.5 (23F77), iPhone 17 Pro.
- Live simulator: **Callshield Oct 17 Validation**, `C914D5D9-4B89-4DF0-8009-B06094CC1E60`. Its name is retained from an earlier session; this report contains new October 19 evidence.
- Automated simulator: **Callshield Oct 19 Automated**, `10469AE2-2454-4954-913E-A1100BE59050`. Live host/token were blanked for its tests.
- Google Voice used the requested `keshavparikh28@gmail.com` account and called **+1 267-509-1164**. Text logs replace the caller's number with `[test caller]`; app screenshots retain that test number. Screenshots are private review evidence.
- Python 3.14.8 was available. Backend checks used the existing isolated test environment in `/private/tmp/callshield-oct17-venv`.
- GitHub CLI was installed but not signed in. The existing downloaded tester artifact passed the repository installer's validation and was installed without displaying its token. Access expiry: **October 24, 03:29 UTC / October 24, 05:29 Warsaw / October 23, 22:29 Central**.
- Callshield was built and launched normally for live calls, without UI-test launch flags. The console confirmed `lobby connected; waiting for incoming calls`. Automated tests were run separately.

All evidence text timestamps use UTC. Add two hours for Warsaw, or subtract five hours for America/Chicago, on this date. Screenshots display the simulator's own Central-time clock; that clock was not changed.

## Results by requested scenario

| Scenario | Observed result | Assessment |
| --- | --- | --- |
| Ordinary human conversation, 45–60 seconds | Keshav subsequently confirmed that he spoke during call 6. That **18-second live human-speech call** saved **Likely human**, **8%**, update **23**, with 10 voice windows. The words spoken were not documented. | Human speech and both pipeline outputs confirmed for this short call. The required **45–60 second** conversation remains **incomplete**. |
| Known synthesized benign speech | About **54 seconds** of macOS Samantha speech through Mac speakers into the Google Voice microphone. Voice: **Likely AI**. Transcript: **No strong scam-language signal**, **5% / update 136** in the accessibility snapshot; the subsequent screenshot shows **3% / update 155**. Saved result: **3% / update 156**. | Both deployed pipelines produced results for this input. One TTS voice and one acoustic setup do not establish general model accuracy. |
| Fictional scam-like speech | **46.10-second** Samantha sample asking for urgent transfers, verification codes, and gift-card numbers, with fictional-test framing. Voice: **Likely AI**. Transcript: **Possible scam language**, **99% / update 63**, then **98% / update 127**. Saved: **98% / update 129**. | Both pipelines updated; scam-language warning appeared. This was synthesized scam speech, not a human scam reading. |
| Caller silence | After the benign sample, Google Voice caller mute was enabled. More than 11 seconds later the current voice result was **Unknown / Waiting for enough caller speech…**, with **Last result: Likely AI** separately labeled. | **Passed** for silence recovery. The last historical result remained visible as intended. |
| Mute/unmute | Callshield's `mute` Off changed to `unmute` On and back to Off. Caller mute was also used for silence. | UI/control state verified. Independent audio isolation was not measured. |
| Speaker | Off → On → Off in Callshield; screenshots show the On state. | UI/control state verified. Physical route quality was not independently heard. |
| Hang-up from app | Callshield returned to Recents. Google Voice subsequently returned to its idle dialer. | **Passed** for termination. No precise propagation-time measurement. |
| Hang-up from caller | Google Voice ended the benign call; Callshield returned to Recents and saved a completed **02:06** call. | **Passed**. |
| Decline | Incoming call disappeared in Callshield; history showed Missed/Unknown. Google Voice remained **Calling…** afterward. | Local dismissal passed; remote call termination did **not** occur. See finding below. |
| Repeat calls / old scores | Calls 4 and 5 started at waiting/listening with no previous score, after the preceding scored call. No restart between them. | **Passed** for inspected new-call resets. |
| Saved details | Benign call preserved AI / 3% / update 156. Scam call preserved AI / 98% / update 129. | **Passed**; both pipeline assessments are present. |
| Two-way audio | Incoming PSTN calls connected and caller speech drove both deployed pipelines. Both endpoints used this Mac; no independent listener confirmed intelligible return audio. | Caller-to-detector path demonstrated; **two-way listening check incomplete**. |

The accessibility snapshot and screenshot are captured sequentially, so advancing scores/update numbers may differ between them. Each is recorded as observed; the saved call record provides the final stored value.

## Findings and setup problems

1. **Decline leaves the telephone caller ringing.** This is reproduced in attempt 7: Callshield returned to Recents, while Google Voice still showed Calling afterward. The caller had to hang up. This matches `backend/AI Deepfake Pipeline/LiveKit Setup/senior_ring.py`, whose `no_answer_fallback` is an explicit stub that does not hang up the caller. Track as an unfinished call-handling behavior, not a model error. Evidence: `screenshots/attempt-7-before-decline.png`, `screenshots/attempt-7-after-decline.png`, `screenshots/attempt-7-caller-still-ringing.jpg`, and the matching text logs.
2. **Initial simulator microphone denial blocked acceptance.** Attempt 2 showed “Allow microphone access in Settings to make a Callshield call.” Its saved outcome was failed. Granting microphone permission and relaunching resolved acceptance. This was an environment prerequisite; no app source fix was applied.
3. **Early acoustic run was uncontrolled.** System output volume was initially 0%. Attempt 3 remained voice-waiting but eventually showed transcript scores of 96%/update 2 and 95%/update 3. No transcript is exposed to verify the actual words recognized. This cannot support a benign-speech false-positive claim or a voice-pipeline failure claim. The next controlled synthetic runs produced both results.
4. **The browser input meter was not reliable proof of speech delivery.** It reported “No sound detected in the last 3 seconds” during an inspected playback interval, yet the same call later produced substantial voice windows and transcript updates. The report relies on observed end-to-end results, not the meter alone.
5. **Extra missed records require correlation before attribution.** Nine invitation records were saved across eight initiated dial attempts. The extra missed invitation at 06:29:56 UTC occurred during the declined-call period. No server logs were available to determine whether it was a repeated invitation, a caller retry, or another cause. The final unanswered call was ended during cleanup.

No controlled synthetic call showed a persistent unavailable pipeline or a previous call's score at its start. This statement is limited to the inspected calls. No accuracy percentage is inferred from these samples.

## Detailed call timeline

Times below are app invitation timestamps from saved history, not estimates of when dialing began.

| Record | Invite UTC / Warsaw | Outcome and observations |
| --- | --- | --- |
| 1 | 06:14:24 / 08:14:24 | First dial had waited for browser microphone permission. Invitation was eventually recorded as Missed; 0 seconds; no assessments. |
| 2 | 06:14:41 / 08:14:41 | Accepted, but Simulator microphone denial blocked the call. Failed; 0 seconds. Permission granted, app relaunched. |
| 3 | 06:15:49 / 08:15:49 | Connected **05:57**. Early synthetic playback began 06:17:32, but output volume was later found at 0%. Voice never left waiting (0 saved windows). Transcript eventually 95.36%, update 3. Mute/unmute and speaker toggles inspected. Ended from app. |
| 4 | 06:22:25 / 08:22:25 | Connected **02:06**. Fresh waiting/listening state captured. App return mic muted. Benign synthetic playback **06:23:00–06:23:54 UTC**, speaker initially set to 40%. AI and low scam-language results appeared. Caller mute then silence recovery captured. Caller hung up. Saved AI with 46 voice windows; transcript 3.19%, update 156. |
| 5 | 06:25:24 / 08:25:24 | Connected **01:24**. Fresh waiting/listening state captured. Google Voice unmuted, app return mic muted. Full fictional scam sample played; exact start/end in `logs/playback-events.txt`. Saved AI with 41 windows; transcript 98.37%, update 129. Ended from app. |
| 6 | 06:27:23 / 08:27:23 | Connected while native simulator windows changed during separate automated tests. Completed **00:18**; saved **Likely human**, 10 windows; transcript **7.68% (displayed 8%), update 23**. Keshav later confirmed: “Yes, I spoke during it.” This establishes live human speech for the short call. The spoken content and acceptance/hang-up actions were not independently documented; the full-duration conversation test remains open. |
| 7 | 06:28:53 / 08:28:53 | Incoming state captured, then Decline clicked. Missed/Unknown; no inherited assessments. Google Voice continued ringing. Caller ended it. |
| Extra | 06:29:56 / 08:29:56 | Additional missed invitation record in the declined-call period; origin unconfirmed. |
| 8 | 06:30:26 / 08:30:26 | Final repeat dial. Native UI capture selected the automated simulator rather than the live window; not claimed as a verified ring/reset test. Saved Missed/Unknown. Caller ended at **06:32:01 UTC / 08:32:01 Warsaw**, and idle dialer was verified. |

## Automated regression results

| Suite | Passed | Failed |
| --- | ---: | ---: |
| iOS Debug: 47 unit + 3 production UI | 50 | 0 |
| iOS Release: 47 unit + 2 production UI | 49 | 0 |
| Backend transcript pipeline | 9 | 0 |
| Worker integration | 15 | 0 |
| Tester tools and cloud-probe runtime contracts | 12 | 0 |
| Ring lifecycle | 18 | 0 |
| Transcript model service | 2 | 0 |
| Node connector | 1 | 0 |
| Cloud contracts / probe checks | 6 | 0 |

The Debug-only analysis-fixture UI test was explicitly excluded from Release because its app fixture is compiled out there. It was included and passed in Debug. The Release result bundle therefore reports 49 selected tests, 0 skipped, rather than counting the excluded case as skipped. No test source was modified.

Several backend suites use fake models or simulated services; their 63 passes verify contracts and control flow. These are separate from the deployed-model phone calls above. Xcode emitted debugger-version diagnostic warnings but both result bundles report Passed with no failures. The app's normal live build and the test build also succeeded.

Reproduce the backend checks with the required test dependencies installed:

```sh
CALLSHIELD_TEST_PYTHON=/private/tmp/callshield-oct17-venv/bin/python python3 docs/testing/2026-10-19/run-backend-checks.py
```

iOS tests used `Callshield`, the clean automated simulator, `CODE_SIGNING_ALLOWED=NO`, and overrides `CALLSHIELD_DEMO=false`, `CALLSHIELD_LIVEKIT_HOST=`, `CALLSHIELD_LOBBY_TOKEN=`. Debug selected all `CallshieldTests` plus `CallshieldUITests/ProductionUITests`; Release additionally excluded `testBothPipelineResultsAreVisibleOnTheCallScreen`. Full Xcode result bundles are at `/private/tmp/callshield-oct19-debug.xcresult` and `/private/tmp/callshield-oct19-release.xcresult`. Sanitized summaries and execution logs are included here.

## Evidence and remaining boundaries

- `logs/call-records-summary.json`: chronological normalized invitation records, final values, durations, and outcomes.
- `logs/saved-test-call-history.json`: sanitized native saved history, including separate voice/transcript objects.
- `logs/attempt-*.txt`: timestamped UI observations. `logs/playback-events.txt` records playback and setup actions.
- `logs/ios-*-summary.json`, `logs/ios-*.log`, and individual backend suite logs: current-run automated evidence.
- `logs/runtime-initial-partial.log`: sanitized stdout for initial startup/first invitations only. Later app launches were detached from that console; this is not a complete runtime log. Later live evidence is from timestamped UI snapshots and saved records.
- `audio/`: generated synthetic source samples, not recordings of private calls. Matching scripts are alongside this report.
- `manifest.json`: file sizes and SHA-256 digests for evidence integrity.

The native automation window captured during attempt 8 is retained as `automated-window-interference.png/.txt`; it is not live-call proof. Some earlier screenshot filenames describe the intended capture stage; use their actual displayed state and paired text. Screenshots were visually checked for the key benign, scam, and silence results.

No headphones or separate physical calling phone was available to the agent. Browser calling from Google Voice exercised the actual incoming telephone route but used a shared Mac audio environment. A full 45–60 second human conversation, independently heard audio in both directions, physical-device/background/lock-screen behavior, and broader model-quality evaluation remain unverified. Keshav confirmed speaking during the 18-second call, which provides short live-human evidence; it does not substitute for the required 45–60 second scenario or confirm the spoken content.

All initiated Google Voice calls were ended. System output was temporarily raised from 0% to 40% for acoustic playback. A later read showed 34% and muted, a change not made by this test script; that latest state was left intact. Microphone access is enabled for Callshield; Google Voice received a one-time microphone grant. Optional browser notifications were blocked. No connection JSON, local configuration, API credential, or private call recording is included. No report was sent to Shrey.
