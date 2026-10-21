# Callshield · Congressional App Challenge 2026

For the full MacBook simulator phone-call test, follow
[MACBOOK_TESTING.md](MACBOOK_TESTING.md). Pull **main**, install the limited tester
settings with `python3 scripts/tester_access.py install`, then run **Callshield**
in Xcode 26 and call **+1 267-509-1164** from a separate phone.

**No LiveKit account, API key or API secret is needed by the tester.** GitHub's
stored secrets generate a limited private app configuration; the installer uses
the tester's existing access to this private repository. The API secret stays on
the server. The on-screen call UI displays separate voice/deepfake and transcript
scam-language results, with unavailable/stale states and saved call assessments.

Both real models and speech recognition run in LiveKit Cloud. No local model
files or backend services are required. See [cloud deployment](deploy/livekit/README.md)
and [the iOS guide](ios/README.md) for implementation details.

For the October 20 meeting materials, longer staged call scripts, video plan, and implementation status, see [the meeting pack](docs/meeting-2026-10-20/MEETING-PACK.md).
