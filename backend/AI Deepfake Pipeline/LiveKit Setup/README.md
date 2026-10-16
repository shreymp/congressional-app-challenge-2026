# LiveKit Setup: `scam-guard` incoming-call agent

For dashboard configuration and running both detection branches, start with
[INCOMING_CALL_SETUP.md](INCOMING_CALL_SETUP.md). The dashboard settings have to be
verified in the CAC project; a checked-in JSON file does not apply them.

Real-time path for incoming calls:

```
Scammer dials grandma's normal cell number
  -> her carrier forwards ALL calls to the LiveKit number (+1 267-509-1164)
  -> LiveKit dispatch rule "cac-inbound" creates a room named  call-...  (prefix + caller
     number + random suffix; use the name LiveKit reports, never rebuild it)
     and dispatches the agent named "scam-guard"
  -> scam-guard rings grandma's open app (senior_ring.py); she answers by joining the same
     room from the app, so the call never leaves LiveKit (see "Ringing the senior's app")
  -> scam-guard (this folder, running on the MacBook) subscribes to the caller's audio only
  -> every ~1 s: last ~4 s of caller speech -> ../best.pt deepfake detector (MPS) -> risk engine
  -> same caller PCM, including silence -> local Vosk -> rolling transcript -> JEV HTTP connector
  -> deepfake level + fresh transcript probability -> existing fusion rule
  -> JSON update published to the room on topic "scam-guard.risk"
  -> grandma's app (later) / tools/watch_risk.py (now) shows it
```

The agent never publishes audio. The phone caller can't hear or detect it.

| File | What it does |
|---|---|
| `agent.py` | The LiveKit worker. Registers as `scam-guard`, starts the ring, finds the SIP caller, streams audio, scores, publishes. |
| `detector_adapter.py` | The only file that knows about the model. Loads `../inference.py` + `../best.pt` on MPS. `DETECTOR=stub` gives fake scores. |
| `audio_window.py` | Rolling 4 s buffer of caller *speech* (simple energy gate drops silence). |
| `risk.py` | Smoothing (in log-odds), levels `listening / elevated / high`, hysteresis. Transcript fusion stub. |
| `transcript_pipeline.py` | Per-call local Vosk recognition and bounded, coalesced HTTP transcript scoring. |
| `dispatch-rule.json` | Dashboard JSON for `cac-inbound` → per-caller `call-` rooms → `scam-guard`. |
| `test_offline.py` | Runs the exact scoring path on a WAV file with no call. Use it to time the model. |
| `tools/watch_risk.py` | Joins a live call room invisibly and prints the agent's updates. |
| `senior_ring.py` | Rings grandma's app for an incoming call and supervises it: answer, no answer, hang-up. No audio code. |
| `test_senior_ring.py` | Offline test of `senior_ring.py` with fakes. No LiveKit, no network, a few seconds. |
| `tools/mint_lobby_token.py` | Prints the lobby token and host the iOS app needs (`Local.xcconfig`). |
| `tools/test_ring.py` | Rings the app with no phone call: fake caller, beeps, level meter for the senior's microphone. |

## One-time setup on the M5 Pro MacBook

1. **Copy `best.pt` over manually.** `.gitignore` excludes `*.pt`, so cloning the repo does NOT bring the 650 MB weights. It must sit at `backend/AI Deepfake Pipeline/best.pt`.
2. Python 3.11+:
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
- Note what the calling phone hears (ringing, silence, or a tone) and when its call timer starts. Expected: ringing, and the timer starts only when grandma answers in the app (see Known issues). With the app closed nobody answers, so it just keeps ringing.

**Step 3: real model on a real call.**
```bash
python agent.py dev
```
Same call. Talk normally, then play one of the TTS WAVs into the calling phone's mic. Watch `p_last` / `level` in `watch_risk.py`.

To collect phone-domain data, set `RECORD_CALLER_AUDIO=1`; caller audio is saved to `recordings/`. **Only on calls where everyone on the call agreed to be recorded** (Illinois requires all-party consent).

## Ringing the senior's app (foreground-only ring)

There is no push notification: the Apple account is a free one, so no PushKit / APNs. The phone
rings only while the Callshield app is open.

```
app open -> stays connected to the lobby room "senior-lobby" as identity "senior"
caller   -> SIP participant joins a call-... room; the caller hears ringing, LiveKit has not answered
agent    -> senior_ring.py sends an invite to the lobby (server API, topic "callshield.incoming"),
            again every 3 s until the senior joins the call room, the caller leaves, or 30 s pass
app      -> native CallKit incoming-call screen; joins the call room silently (no microphone)
answer   -> the app publishes its microphone. That is what makes LiveKit answer the phone call.
```

| What happens | What the agent does |
|---|---|
| Caller hangs up, at any time | Stops. The app ends the CallKit call when the caller's participant leaves. |
| Not answered within `RING_TIMEOUT_SEC` (30 s), or the app leaves the room without answering (decline, or the phone's own ring timeout) | Logs it and calls `no_answer_fallback()` exactly once. **That function is a stub**: "agent takes a message + notify family" goes there later. The caller is not hung up. |
| Senior hangs up after answering (or the app dies) and is not back within 5 s | Deletes the room, which disconnects the phone caller. |

The agent logs each step once (`scam-guard.ring`): `incoming call ... number sent to the app`,
`senior app not connected to lobby`, `invite sent`, `senior joined`, `senior answered`, `no answer`,
`senior hung up`. Offline test of this logic: `python test_senior_ring.py`.

### Wire contract (must match the iOS app exactly)

- Lobby room `senior-lobby`; senior identity `senior` in the lobby and in the call room.
- One reliable data message on topic `callshield.incoming`, addressed to the senior identity only. UTF-8 JSON:
  ```json
  {"type": "incoming_call",
   "callUUID": "<uuid4; the same on every re-send; the app's CallKit UUID>",
   "room": "<call room name>",
   "token": "<LiveKit token for identity senior, this room only>",
   "handle": "<caller's number (sip.phoneNumber); may be empty>",
   "callerIdentity": "<participant identity of the caller>"}
  ```
  Optional key: `callerName`. The token allows join, subscribe and publishing a microphone; no data; valid 10 minutes (`RING_TIMEOUT_SEC` + 6 minutes if that is longer). The open-source server sends a refreshed token right after the session starts and every 5 minutes, and the Swift SDK presents it on a reconnect; the long life is a margin, because LiveKit Cloud's refresh behaviour is not public.
- The app ignores a `callUUID` it has already handled, and treats the `callerIdentity` participant leaving as "caller hung up".
- The LiveKit host is not in the message. The app has it, and its lobby token, from `ios/Configuration/Local.xcconfig`.

### Tools

```bash
python tools/mint_lobby_token.py            # prints CALLSHIELD_LIVEKIT_HOST and CALLSHIELD_LOBBY_TOKEN (30 days; --days N)
python tools/test_ring.py                   # ring -> answer -> two-way audio -> hang-up, with NO phone call
python tools/test_ring.py --handle +13125550123 --duration 300
```

Both read `LIVEKIT_URL`, `LIVEKIT_API_KEY` and `LIVEKIT_API_SECRET` from `.env.local`. Paste the two
lines from `mint_lobby_token.py` into `ios/Configuration/Local.xcconfig` (gitignored; the token is a
credential) and rebuild the app. The token expires: mint a new one before then.

The lobby token is a bearer credential baked into the app. Whoever extracts it can join the lobby as
`senior`, receive every invite (each carries a call token), join that call room, hear the caller and
speak into the call; and it kicks the real app off the lobby. Keep it only in `Local.xcconfig`, use a
short `--days` for demos, and if it may have leaked change `SENIOR_LOBBY_ROOM` (the old token only
works for the old room) and mint a new token.

`test_ring.py` is a fake caller in a throwaway `ringtest-...` room (scam-guard is not dispatched
there, so no risk updates). It plays quiet beeps as its microphone and invites the app with the
same code the agent uses. Open the app first, then check: the phone rings and shows the `--handle`
number; answering prints `senior answered`, you hear the beeps, and the level meter moves when you
talk into the phone; Ctrl+C makes the fake caller leave and the app should end the call; hanging up
on the phone deletes the room after 5 s, as the agent does.

### Settings

Nothing has to be set: the defaults are in `senior_ring.py`. Optional overrides: `SENIOR_IDENTITY`,
`SENIOR_LOBBY_ROOM`, `RING_TIMEOUT_SEC` (see `.env.example`; 5 to 600 seconds, anything else is
ignored with a warning in the log and the default 30 is used). Locally they go in `.env.local`. On
LiveKit Cloud `.env` files are not copied into the image, so set them as secrets:
`lk agent update-secrets --secrets "RING_TIMEOUT_SEC=45"` (this restarts the agent). `LIVEKIT_URL`,
`LIVEKIT_API_KEY` and `LIVEKIT_API_SECRET` are injected by LiveKit Cloud; the agent uses them to
mint the call token and to call the server API. If you change the identity or lobby room, mint a
new lobby token for the app.

## Known issues / open questions

- **Thresholds are probably wrong for phone audio.** The config thresholds (0.99999 / 0.9999999) come from the training test split. Real LiveKit audio will shift the scores. Use Step 3 and `recordings/` to recalibrate, then set `THRESHOLD_ELEVATED` / `THRESHOLD_HIGH` in `.env.local`.
- **LiveKit answers the call only when someone publishes audio (to confirm on a live call).** An earlier version of this file guessed that LiveKit answers as soon as the call arrives. Per LiveKit's SIP docs and the open-source SIP service it does not: the caller hears ringing, the SIP participant waits in the room with `sip.callStatus=ringing`, and the call is answered once another participant publishes an audio track. scam-guard never publishes audio, so grandma's microphone is the answer. Consequences: the agent gets no caller audio, so no scores, before she answers; and because all calls are forwarded, her carrier voicemail never triggers, so "no answer" is ours to handle (`no_answer_fallback()`, a stub today). Still to confirm on a live call: that a LiveKit-rented number behaves this way, and how long LiveKit lets it ring before giving up (3 minutes in the open-source default).
- **A second ring is possible after an agent crash.** If LiveKit re-dispatches the agent into a call that is still ringing, the new job sends a new `callUUID`. Harmless if the app already joined the call room (no invite is sent then); if grandma had declined, her phone rings again. The same happens if the app is quit and reopened inside the ring window for a call it never joined: the app remembers handled `callUUID`s in memory only, so the repeated invite rings again. That second case is arguably right, since the phone caller is still ringing.
- **An early decline is reported as a timeout.** The agent only learns of a decline once the app has been in the call room. Declining while the app is still joining, Do Not Disturb refusing the CallKit call, or a failed join all show up as `no_answer_fallback(reason="timeout")` at the end of the ring window, not as `"declined"` after 5 s. The app ignores the repeated invites for that call meanwhile. The obvious shortcut (treat "back in the lobby" as a decline) is wrong: the app also leaves and rejoins the lobby when it is backgrounded or loses its network.
- **Transcript branch needs its local models and services running.** Set `VOSK_MODEL_PATH`, start the JEV model service and connector, then run the agent. Missing STT/model services produce a null transcript probability and an explicit state; deepfake scoring continues. The fusion rule is still experimental and has not been calibrated on real-call prefixes. See [INCOMING_CALL_SETUP.md](INCOMING_CALL_SETUP.md).
- **Energy gate, not a real VAD.** Fine for testing. Swap for Silero VAD if quiet speech is skipped or noise is scored.
- `sip.callStatus` exists as a SIP attribute; we log it, and the ring skips participants whose status is `dialing` (outbound calls). The `ringing` to `active` change is not used.

