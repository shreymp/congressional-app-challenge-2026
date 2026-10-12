# LiveKit Setup: `scam-guard` call agent (Phase 1–2)

Real-time path for incoming calls:

```
Scammer dials grandma's normal cell number
  -> her carrier forwards ALL calls to the LiveKit number (+1 267-509-1164)
  -> LiveKit dispatch rule "cac-inbound" creates room  call-<caller-number>
     and dispatches the agent named "scam-guard"
  -> scam-guard (this folder, running on the MacBook) subscribes to the caller's audio only
  -> every ~1 s: last ~4 s of caller speech -> ../best.pt deepfake detector (MPS) -> risk engine
  -> JSON update published to the room on topic "scam-guard.risk"
  -> grandma's app (later) / tools/watch_risk.py (now) shows it
```

The agent never publishes audio. The phone caller can't hear or detect it.

| File | What it does |
|---|---|
| `agent.py` | The LiveKit worker. Registers as `scam-guard`, finds the SIP caller, streams audio, scores, publishes. |
| `detector_adapter.py` | The only file that knows about the model. Loads `../inference.py` + `../best.pt` on MPS. `DETECTOR=stub` gives fake scores. |
| `audio_window.py` | Rolling 4 s buffer of caller *speech* (simple energy gate drops silence). |
| `risk.py` | Smoothing (in log-odds), levels `listening / elevated / high`, hysteresis. Transcript fusion stub. |
| `test_offline.py` | Runs the exact scoring path on a WAV file with no call. Use it to time the model. |
| `tools/watch_risk.py` | Joins a live call room invisibly and prints the agent's updates. |

## One-time setup on the M5 Pro MacBook

1. **Copy `best.pt` over manually.** `.gitignore` excludes `*.pt`, so cloning the repo does NOT bring the 650 MB weights. It must sit at `backend/AI Deepfake Pipeline/best.pt`.
2. Python 3.10+:
   ```bash
   cd "backend/AI Deepfake Pipeline/LiveKit Setup"
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. `cp .env.example .env.local`, then fill in `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` from LiveKit Cloud → Settings → API keys (project **CAC**). The URL is on the project's settings page.

## Test order (each step must pass before the next)

**Step 1: model speed, no call (5 min).**
```bash
python test_offline.py "../melo_everyday_03_en-us_s1.1.wav"
python test_offline.py "../ov2_shrey_everyday_03_en-us_s1.1_t0.3_wm1.wav" --phone
```
Check the first line says `device=mps`, and the final `inference ms: median ...` is well under 1000. The first run downloads the XLS-R config from Hugging Face.

**Step 2: call plumbing with fake scores.**
```bash
DETECTOR=stub python agent.py dev
```
- On a test phone, turn on *forward all calls* to `+1 267-509-1164` (carrier code varies; often `*72` Verizon, `**21*` AT&T/T-Mobile).
- From a *different* phone, call the test phone.
- In the agent's terminal, find the `SIP attributes:` log. **Record what `sip.phoneNumber` shows: the real caller, or the forwarding phone?** That decides whether grandma's app can show caller ID.
- In a second terminal: `python tools/watch_risk.py` and watch updates arrive once there has been ~3 s of talking.
- Note what the calling phone hears (ringing, silence, or a tone) and whether its call timer starts immediately. That tells us when LiveKit answers.

**Step 3: real model on a real call.**
```bash
python agent.py dev
```
Same call. Talk normally, then play one of the TTS WAVs into the calling phone's mic. Watch `p_last` / `level` in `watch_risk.py`.

To collect phone-domain data, set `RECORD_CALLER_AUDIO=1`; caller audio is saved to `recordings/`. **Only on calls where everyone on the call agreed to be recorded** (Illinois requires all-party consent).

## Known issues / open questions

- **Thresholds are probably wrong for phone audio.** The config thresholds (0.99999 / 0.9999999) come from the training test split. Real LiveKit audio will shift the scores. Use Step 3 and `recordings/` to recalibrate, then set `THRESHOLD_ELEVATED` / `THRESHOLD_HIGH` in `.env.local`.
- **When LiveKit answers the call isn't documented.** LiveKit's docs say the caller hears a tone until LiveKit responds, then keeps hearing it "until another participant publishes tracks." So the call is likely answered as soon as it reaches LiveKit, before grandma picks up. Side effect: her carrier voicemail never triggers, so "no answer" must be handled by our system. Confirm in Step 2.
- **Transcript branch is not connected.** `risk.combine()` takes a transcript probability; nothing produces one yet. Next: speech-to-text on the same stream → `POST http://localhost:3000/v1/jev/probability` (the Transcript-Based Detector).
- **Energy gate, not a real VAD.** Fine for testing. Swap for Silero VAD if quiet speech is skipped or noise is scored.
- `sip.callStatus` exists as a SIP attribute; we log it but don't act on it yet.
