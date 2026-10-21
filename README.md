# Callshield · Congressional App Challenge 2026

## Shrey: 15-second voice verdict and cumulative AI score

The `shrey` branch now includes `main` through `dca989c` (39 commits brought
forward, with no divergent Shrey commits), plus the voice-analysis changes below.
Use **shrey** to test this feature. This branch update does not deploy the worker.

- Connected calls start with **Analyzing**. Results can appear earlier, and an
  initial assessment is finalized at **15 seconds after the call connects**,
  including pauses. It shows **Human**, **Likely AI**, or **Inconclusive**. A
  detected processing/connection failure shows **Analysis unavailable**.
- Results show a consistent **AI score: N/100**, where higher means stronger AI
  evidence. When no usable result exists, the score is unavailable rather than
  invented. Both the verdict and score continue updating as new audio arrives.
- Distinct audio segments contribute to a bounded, speech-weighted call summary.
  Pauses retain accumulated evidence. Sustained recent AI-like speech also gets
  its own warning, so a long human introduction cannot hide a later change.
- This version uses explicit heuristic thresholds, **not a calibrated probability**.
  Real phone-call calibration, accuracy claims and frequency of inconclusive
  outcomes remain unvalidated. The model weights have not changed.

See [the feature implementation and validation notes](docs/CUMULATIVE_VOICE_ANALYSIS.md)
for the exact scoring formula, deadline behavior, wire compatibility, tests and
rollout requirements. Both the updated iOS app and worker are needed for scores.

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
