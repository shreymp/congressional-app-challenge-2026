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
  -> distinct 4 s audio windows -> ../best.pt deepfake detector -> cumulative call evidence
  -> same caller PCM, including silence -> local Vosk -> rolling transcript -> JEV HTTP connector
  -> deepfake level + fresh transcript probability -> existing fusion rule
  -> JSON update published to the room on topic "scam-guard.risk"
  -> the iPhone app displays the voice assessment; tools/watch_risk.py can inspect updates
```

After the senior answers, the agent plays **"This call is being recorded."** into the
call room, then starts caller analysis. Both the caller and the answered app receive
the announcement. It never publishes the announcement while the phone is ringing.
If the asset is missing, invalid, or playback fails/times out, transcription, deepfake
analysis and optional caller recording stay off for that call; the ring/hang-up
supervisor continues and the app receives an unavailable status.

The cloud image generates and bundles the fixed clip at build time using eSpeak NG
and SoX. There is no per-call TTS request or API key. For a local worker, install
`espeak-ng` and `sox` (on macOS: `brew install espeak-ng sox`), then run from the repo root:

```sh
python3 deploy/livekit/generate_recording_notice.py \
  --output 'backend/AI Deepfake Pipeline/LiveKit Setup/assets/recording_notice.wav'
```

This announcement is a disclosure, not a consent check. It does not enable audio
storage: `RECORD_CALLER_AUDIO` still defaults to `0`. Obtain the required permission
before enabling storage. Diagnostic backend probes skip the announcement and ringing.

| File | What it does |
|---|---|
| `agent.py` | The LiveKit worker. Registers as `scam-guard`, starts the ring, finds the SIP caller, streams audio, scores, publishes. |
| `recording_notice.py` | Plays the fixed notice and drains playback before caller audio processing can start. |
| `detector_adapter.py` | The only file that knows about the model. Loads `../inference.py` + `../best.pt` on MPS. `DETECTOR=stub` gives fake scores. |
| `audio_window.py` | Contiguous 4 s audio buffer; fixed, adaptive or Silero speech gate, clipping check and digital-silence guard. Natural pauses are preserved. |
| `speech_vad.py` | Optional Silero VAD (`SPEECH_GATE=silero`) used by the speech gate. |
| `pipeline_config.py` | Immutable scoring settings (`SPEECH_GATE`, `DIGITAL_SILENCE_MAX_SEC`, current-evidence cohort flags). |
| `current_evidence.py` | Opt-in finite-horizon "current speech" engine for the v2 contract (off by default). |
| `scoring.py` | Shared live/file scoring session; distinct windows, inference state and call evidence retained through silence. |
| `risk_protocol.py` | Versioned caller/room/stream envelope for the iPhone app. |
| `risk.py` | Bounded cumulative whole-call evidence (optional checkpoint-bound Platt calibration), legacy EMA, transcript fusion stub. |
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
Check the first line says `device=mps`, and the final `inference ms: median ...` is well under 1000. The XLS-R architecture config is pinned in `../architecture/config.json`; startup verifies the architecture, checkpoint and detector-config hashes (`../model_integrity.json`) before warmup. After retraining, re-pin with `python ../model_integrity.py --pin <weights folder>`.

**Step 2: call plumbing with fake scores.**
```bash
DETECTOR=stub python agent.py dev
```
- On a test phone, turn on *forward all calls* to `+1 267-509-1164` (carrier code varies; often `*72` Verizon, `**21*` AT&T/T-Mobile).
- From a *different* phone, call the test phone.
- In the app, inspect the incoming caller number. **Record whether it is the real caller or the forwarding phone.** That decides whether grandma's app can show caller ID.
- In a second terminal: `python tools/watch_risk.py` and watch updates after a complete 4 s window with enough usable caller speech.
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
| Not answered within `RING_TIMEOUT_SEC` (30 s), or the app leaves the room without answering (decline, or the phone's own ring timeout) | Waits 5 s after the app leaves to allow reconnection, or until the ring window ends. Calls `no_answer_fallback()` exactly once, then deletes the room to disconnect the caller. The hook currently only logs; voicemail and family notifications are not implemented. |
| Senior hangs up after answering (or the app dies) and is not back within 5 s | Deletes the room, which disconnects the phone caller. |

The agent logs each step once (`scam-guard.ring`): `incoming call ... number sent to the app`,
`senior app not connected to lobby`, `invite sent`, `senior joined`, `senior answered`, `no answer`,
`senior hung up`. Room deletion is attempted up to 3 times with a 5 s timeout per request;
if the caller remains connected, supervision returns `cleanup_failed` and logs an error instead
of reporting a successful hang-up. A late answer cannot cancel cleanup after a no-answer decision.
Offline test of this logic: `python test_senior_ring.py`.

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

- **Thresholds are probably wrong for phone audio.** The config thresholds (0.99999 / 0.9999999) come from the training test split. Real LiveKit audio will shift the scores. The stored probabilities are float32-saturated (0.9999998807907104 is 1 - 2·2⁻²⁴), so prefer logit-space thresholds: `logit_threshold_eer` / `logit_threshold_1pct_fpr` in `detector_config.json` or `THRESHOLD_ELEVATED_LOGIT` / `THRESHOLD_HIGH_LOGIT`. Select them from consented, independent calibration recordings and raw logits, then freeze them before held-out evaluation. Do not tune on the reused demo clips. See [docs/EVIDENCE_CONTRACT.md](docs/EVIDENCE_CONTRACT.md).
- **LiveKit answers the call only when someone publishes audio (to confirm on a live call).** An earlier version of this file guessed that LiveKit answers as soon as the call arrives. Per LiveKit's SIP docs and the open-source SIP service it does not: the caller hears ringing, the SIP participant waits in the room with `sip.callStatus=ringing`, and the call is answered once another participant publishes an audio track. scam-guard never publishes audio, so grandma's microphone is the answer. Consequences: the agent gets no caller audio, so no scores, before she answers; and because all calls are forwarded, her carrier voicemail never triggers, so "no answer" is ours to handle (the ring supervisor disconnects unanswered callers; `no_answer_fallback()` is an optional notification hook). Still to confirm on a live call: that a LiveKit-rented number behaves this way, and how long LiveKit lets it ring before giving up (3 minutes in the open-source default).
- **A second ring is possible after an agent crash.** If LiveKit re-dispatches the agent into a call that is still ringing, the new job sends a new `callUUID`. Harmless if the app already joined the call room (no invite is sent then); if grandma had declined, her phone rings again. The same happens if the app is quit and reopened inside the ring window for a call it never joined: the app remembers handled `callUUID`s in memory only, so the repeated invite rings again. That second case is arguably right, since the phone caller is still ringing.
- **An early decline is reported as a timeout.** The agent only learns of a decline once the app has been in the call room. Declining while the app is still joining, Do Not Disturb refusing the CallKit call, or a failed join all show up as `no_answer_fallback(reason="timeout")` at the end of the ring window, not as `"declined"` after 5 s. The app ignores the repeated invites for that call meanwhile. In both cases the agent deletes the call room after the no-answer decision, so the caller is disconnected; an early decline can take the full ring window. The obvious shortcut (treat "back in the lobby" as a decline) is wrong: the app also leaves and rejoins the lobby when it is backgrounded or loses its network.
- **Transcript branch needs its local models and services running.** Set `VOSK_MODEL_PATH`, start the JEV model service and connector, then run the agent. Missing STT/model services produce a null transcript probability and an explicit state; deepfake scoring continues. The fusion rule is still experimental and has not been calibrated on real-call prefixes. See [INCOMING_CALL_SETUP.md](INCOMING_CALL_SETUP.md).
- **Speech gate.** The default fixed gate misses quiet speech and passes DTMF and tonal music, which the current model scores near logit 50 (strongly AI). `SPEECH_GATE=silero` uses a trained VAD that rejected every non-speech control in development checks; it still needs a real-model replay and a live-call check before becoming the default. A digital-silence guard (on by default, `DIGITAL_SILENCE_MAX_SEC=.2`) skips windows with more than 0.2 s of exact zeros: such windows made real human speech score above clean AI speech. See [docs/EVIDENCE_CONTRACT.md](docs/EVIDENCE_CONTRACT.md).
- `sip.callStatus` exists as a SIP attribute; we log it, and the ring skips participants whose status is `dialing` (outbound calls). The `ringing` to `active` change is not used.


## iPhone voice assessment contract (schema 1)

Deploy the updated agent together with the updated iPhone app. Topic: `scam-guard.risk`, reliable data. Every message includes `schema: 1`, `room`, `callerIdentity`, `streamID` (UUID per scoring session), positive increasing `sequence`, and `model` (`real` or `stub`). The app requires a LiveKit agent participant as sender. The SDK exposes this through [Participant.kind](https://docs.livekit.io/reference/client-sdk-swift/documentation/livekit/participant/); data and reconnect callbacks follow the pinned [RoomDelegate API](https://github.com/livekit/client-sdk-swift/blob/2.17.0/Sources/LiveKit/Protocols/RoomDelegate.swift).

New evidence additionally carries `method: call-evidence-v1`, `state`, `score` (a heuristic 0–100 AI score), `score_kind: heuristic`, `recent_ai`, and `max_ai_run`. See [the feature notes](../../../docs/CUMULATIVE_VOICE_ANALYSIS.md) for exact aggregation, 15-second app deadline, limitations and rollout.

`type: status` carries `state: waiting | analyzing | unavailable`. `type: risk` carries `deepfake` with `level`, `updates`, `human_steps`, `p_last`, `p_smoothed`, `logit_last`, `logit_smoothed`. Existing diagnostic fields (`level`, `transcript`, `infer_ms`, `voiced_sec`, `t`) remain available to the watcher. The app derives its voice label from `deepfake`, never from the combined `level`. A heartbeat sends current state every two seconds; new scores use distinct four-second audio windows. Silence for six seconds clears only the rolling audio window, retaining call evidence and verdicts. Inference longer than ten seconds reports unavailable without starting more work. A model-load or per-window failure leaves calling operational.

Offline checks from the repository root:

```powershell
.venv/Scripts/python.exe -m unittest discover -s "backend/AI Deepfake Pipeline/LiveKit Setup" -p "test_*integration.py" -v
.venv/Scripts/python.exe "backend/AI Deepfake Pipeline/LiveKit Setup/test_senior_ring.py"
.venv/Scripts/python.exe "backend/AI Deepfake Pipeline/LiveKit Setup/test_offline.py" path/to/speech.wav --phone --json-out path/to/messages.json
```

On macOS use the corresponding virtual environment's `python` command. `--json-out` exports the exact app envelope without a LiveKit connection. Shared fixtures under `ios/CallshieldTests/Fixtures/deepfake-wire.json` are generated by the production Python risk engine and consumed by Swift tests; regenerate intentionally with `test_integration.py --write-fixtures` after changing the contract.
