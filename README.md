# Callshield · Congressional App Challenge 2026

For the MacBook tester, start with [MACBOOK_TESTING.md](MACBOOK_TESTING.md).
Use updated **main**, Xcode 26 and the **Callshield** scheme in
`ios/Callshield.xcodeproj`.

The deployed LiveKit worker runs both the real AI voice/deepfake model and
Vosk → JEV transcript inference. The Mac only runs the app and test tools.
Configure private LiveKit access locally, then use `cloud-probe` to test both
hosted pipelines and `full-call` to test a real simulator call through them.
No local model downloads are required for hosted testing.

See [cloud deployment](deploy/livekit/README.md) for worker deployment and
[the iOS guide](ios/README.md) for the app. Simulator testing uses in-app call
controls; physical iPhone/CallKit and cellular routing have separate checks.
