# Deepfake connector validation — October 16, 2026

Branch: `deepfake-connector`. Integration target: native Callma production app.

## Completed on Windows

- Nine offline audio/risk/protocol tests passed. They cover insufficient speech, silence, distinct fresh windows, sustained evidence, hysteresis, invalid scores/configuration, in-flight results after a pause, slow inference, failure recovery and shared Swift fixtures.
- Four production agent orchestration tests passed with fake rooms/audio: real-path publication, missing-model status, inference failure, cancellation and stream closure. They make no LiveKit connections.
- All 18 existing ringing regression tests passed, including scoring failure isolation from ringing, answer/decline, timeouts, reconnect grace and hang-up.
- The agent imports and registers with installed `livekit-agents 1.8.8`, `livekit-api 1.2.2` and `livekit 1.1.20`. `pip check` passed. The root Python environment lock includes these missing runtime dependencies and the versions their resolver requires.
- The real `best.pt` checkpoint loaded from disk with the cached XLS-R configuration, on CPU with four OpenMP threads. No model or audio was uploaded.
- The existing 15-second microphone recording, resampled through the phone simulation, produced 11 scored windows: median 420 ms, maximum 476 ms. Its evidence met the app's human-label rule after the third window. These are local fixture observations, not an accuracy estimate.
- The existing 5.7-second AI WAV did not contain three seconds of audio above the current energy gate and correctly yielded no verdict. Repeating the same clip four times in a temporary local file provided enough speech: 16 windows, median 646 ms, maximum 666 ms, sustained `high` from the third scored window (audio time 9 seconds). Repetition is a connector smoke test, not independent evaluation data.
- Exact real-model app messages are saved locally under the gitignored `work/` directory. Generated raw-audio derivatives are also confined there and are not bundled with the app.
- Python compilation and Xcode project regeneration completed. New Swift sources and JSON fixtures are included by the generator.

Sandbox note: even a minimal `asyncio.sleep` stalled in this Windows sandbox. The timer-dependent offline tests above passed when run outside the sandbox. Their test fixtures still use no network. Stalled diagnostic/test processes were stopped.

## Added but requires a Mac to execute

`DeepfakeIntegrationTests` verifies Python fixture decoding, all voice/status mappings, rejection of malformed/spoofed/mismatched/stale packets, agent restarts, timeout/recovery, pre-answer/stale-call isolation, last-result retention, saved-history compatibility and refresh preservation.

Run from the repository root with Xcode 26 or later:

```sh
xcodebuild -project ios/Callma.xcodeproj -scheme Callma \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' \
  -derivedDataPath /tmp/callshield-deepfake-build \
  -parallel-testing-enabled NO CODE_SIGNING_ALLOWED=NO test
```

Windows has no Xcode or iOS simulator. Swift compilation, XCTest execution and rendered iPhone UI verification have not been performed for this change. Prior native validation reports describe earlier versions only.

## Remaining integration checks

1. Set the LiveKit host/lobby token in the untracked `ios/Configuration/Local.xcconfig`, keep production mode enabled, and start the updated agent with its model weights and LiveKit credentials. No credential values are committed by this change.
2. On a physical iPhone, accept an incoming forwarded call and confirm waiting → analyzing → result, mute/speaker audio, history details and caller hang-up. Calling remains foreground-only under the existing ringing architecture.
3. Interrupt/reconnect the network or stop/restart the detector agent; confirm analysis becomes unavailable, the call can continue when media remains connected, and new valid assessments recover.
4. Confirm actual phone-audio performance and calibrate thresholds/energy gating against representative callers. No live audio stream was available here. Transcript risk, carrier outgoing-call audio, background VoIP push and voicemail remain outside this voice connector and retain their existing service limitations.

# Shrey cumulative-scoring update

The results below describe the earlier connector and its overlapping-window
scoring; they are historical, not validation of the new aggregation method.
Current behavior, local checks and remaining phone-domain validation are recorded
in [CUMULATIVE_VOICE_ANALYSIS.md](../docs/CUMULATIVE_VOICE_ANALYSIS.md).
