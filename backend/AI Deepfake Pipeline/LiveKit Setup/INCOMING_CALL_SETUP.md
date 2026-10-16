# Incoming calls in LiveKit project CAC

This wires the existing iOS foreground calling flow and both detection branches.
It does not add a new calling website. LiveKit dashboard configuration and a running
worker are both required; uploading a dispatch rule alone does not run Python.

For a reproducible MacBook simulator setup, start with [MACBOOK_TESTING.md](../../../MACBOOK_TESTING.md).

## Dashboard verification — 2026-10-16

Browser inspection of CAC confirmed the existing inbound configuration:

- Number `+12675091164` is active and assigned to `SDR_W3CDWuY9RKkD`.
- Rule `cac-inbound` uses Individual rooms with prefix `call-`.
- Its phone-number selector includes `+12675091164`.
- Agent dispatch targets `scam-guard`, deployment `production`, with Restart on failure.
- Production version `8Fc2VCW3LSui` reports source commit `d8baca2` on `main`.
  This predates the transcript integration on `codex/livekit-transcript-pipeline`.
- The agent status was `sleeping`; that alone does not prove a runtime failure.
  No calls appeared in the past-24-hours call view, so no real-call verification
  was possible during this inspection.
- The Secrets page lists `DETECTOR` and `RECORD_CALLER_AUDIO`. Existing values
  are write-only in the update form and were not verified or changed.

The phone routing already matches the intended setup, so no duplicate rule,
new number, or dashboard settings changes were needed. The remaining work is
runtime deployment: provision the real `best.pt`, Vosk and JEV artifacts, run
the integrated worker and model services, and perform the call checks below.
The current repository tree contains no Dockerfile or `livekit.toml` for
reproducing the existing hosted deployment. Do not treat the old hosted version
as evidence that the new pipeline is deployed. If using the documented local
worker route, avoid leaving the old hosted worker eligible for the same agent
dispatch; verify that calls reach the intended version.

## Dashboard

Open [the CAC project](https://cloud.livekit.io/projects/p_5xz2jnm4y7j/overview).

1. In **Telephony → Phone numbers**, inspect the number already provisioned. The
   repository documents `+1 267-509-1164`; verify the current number in the dashboard.
   Use the existing number rather than renting another one.
2. In **Telephony → Dispatch rules**, inspect `cac-inbound`. Edit the existing rule
   if present; create it only if absent. In the JSON editor use `dispatch-rule.json`:

   ```json
   {
     "name": "cac-inbound",
     "rule": { "dispatchRuleIndividual": { "roomPrefix": "call-" } },
     "roomConfig": { "agents": [{ "agentName": "scam-guard" }] }
   }
   ```

3. Assign that rule to the existing LiveKit phone number. This file intentionally
   has no trunk filter: in a project with several inbound trunks, preserve the
   existing intended trunk restrictions instead of broadening them. A LiveKit
   phone number needs no third-party inbound trunk. If the number is provided by
   Twilio/Telnyx instead, configure its inbound trunk and provider routing too.
4. Verify the registered worker is named **`scam-guard`**, exactly. For the current
   Mac/MPS setup it runs on the Mac using `agent.py dev`; it is not a hosted agent
   merely because a dispatch rule names it. Do not deploy a second copy while that
   worker is already running. In **Agents**, check worker/session availability and
   inspect call sessions for dispatch errors.
5. In **Settings → API keys**, use project credentials in `.env.local`, which is
   ignored by Git. Copy the project's actual WebSocket URL; the project ID is not
   that URL. Keep the API secret on the backend.

References: [dispatch rules](https://docs.livekit.io/telephony/accepting-calls/dispatch-rule/),
[phone numbers](https://docs.livekit.io/telephony/start/phone-numbers/), and
[call testing](https://docs.livekit.io/telephony/testing/).

## Local worker and models

Use Python 3.11+ and Node 22+. From the repository root:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r 'backend/AI Deepfake Pipeline/LiveKit Setup/requirements.txt'
pip install -r 'backend/Transcript-Based Detector/requirements-model.txt'
python3 ios/scripts/setup_posttrained_jev.py
```

The last command verifies the published V1/V2 ONNX bundles and stores them in the
existing iOS resources directories. It requires access to the private repository;
see `backend/jev-posttrain/README.md`. The backend defaults to the caller-only V2
bundle; it does not use the upstream ten-behavior model as a scam probability.

Copy the real deepfake weights to `backend/AI Deepfake Pipeline/best.pt` as before.
They are not in Git. Keep `detector_config.json` and `inference.py` alongside them.
Download and extract [Vosk's small US English model](https://alphacephei.com/vosk/models)
into `backend/AI Deepfake Pipeline/LiveKit Setup/models/`, so that
`models/vosk-model-small-en-us-0.15/` contains the model files, not another nested
directory. Vosk stays local and is not automatically downloaded at worker startup.

```sh
cd 'backend/AI Deepfake Pipeline/LiveKit Setup'
cp .env.example .env.local
```

Fill the three LiveKit credentials in `.env.local`. Its default paths now enable
both branches. Relative `VOSK_MODEL_PATH` is resolved against this directory.

## Start three processes

Keep all three running, each in its own terminal with the virtual environment active.
Commands below are from the repository root on the same machine:

```sh
# Terminal 1: actual ONNX call model; binds only to loopback and verifies bundle hashes
python3 'backend/Transcript-Based Detector/model_service.py'

# Terminal 2: existing JEV connector
cd 'backend/Transcript-Based Detector'
JEV_MODEL_URL=http://127.0.0.1:8000/predict npm start

# Terminal 3: named LiveKit worker, deepfake and Vosk models prewarmed
cd 'backend/AI Deepfake Pipeline/LiveKit Setup'
python3 agent.py dev
```

On PowerShell, activate `.venv\Scripts\Activate.ps1` and in Terminal 2 set
`$env:JEV_MODEL_URL='http://127.0.0.1:8000/predict'` before `npm start`.

Check `http://127.0.0.1:8000/health` returns `modelLoaded: true` and
`http://127.0.0.1:3000/health` returns `modelConfigured: true`. Then POST
`{"transcript":"Caller: Read me the code your bank sent you."}` to
`http://127.0.0.1:3000/v1/jev/probability` and verify a finite probability is returned.
The connector's health reports configuration; the successful POST proves connectivity.
Neither service should be exposed publicly without authentication.

For LiveKit Cloud hosting, package the model artifacts and run the model service and
connector on reachable backend infrastructure. `127.0.0.1` inside a hosted worker
does not point to your Mac. This guide uses the existing local Mac worker; it does
not claim to deploy a hosted container or upload model weights.

## Verify a call

1. Mint a lobby token with `python3 tools/mint_lobby_token.py`, configure the iOS
   app as described in README.md, and open the app. Its identity is `senior`, in
   `senior-lobby`. The token is a credential; do not commit it.
2. Call the LiveKit number from another phone. Confirm one `call-...` room and a
   `scam-guard` job appear, and that the app rings. Answer in the app.
3. Run `python3 tools/watch_risk.py`. Once there is enough speech, verify the
   `scam-guard.risk` message includes both `deepfake` and `transcript` objects.
   A working transcript path shows `state: monitoring`, a non-null `probability`,
   and advancing revisions. It carries no raw transcript text.
4. Stop the JEV connector temporarily. The transcript should become
   `jev_unavailable` with a null probability while deepfake updates continue.
   Restart the connector; the latest context is retried automatically.
5. Hang up in the app. Confirm room deletion and phone disconnection. Also test
   caller hang-up and a call that is not answered. The existing no-answer handler
   is still a stub; it does not take voicemail or notify family.

The worker sends caller PCM, including silence, to Vosk. Only the deepfake branch
uses the speech energy gate. Each call has its own recognizer and bounded context;
new partial hypotheses replace earlier partials. HTTP work runs off the audio loop,
one request at a time, with newest-context coalescing. Overrun, missing models,
service errors, and stale probabilities cannot supply a transcript escalation.

The existing fusion rule is unchanged: voice `high` plus transcript score ≥0.8
yields `prevention`; that is a risk label, not an implemented automatic intervention.
The models and that threshold still require real-call and prefix-level validation.
Ringing remains foreground-only; no push notifications were added.

## Automated checks

```sh
cd 'backend/AI Deepfake Pipeline/LiveKit Setup'
python3 -m unittest -v test_transcript_pipeline
cd '../../Transcript-Based Detector'
python3 -m unittest -v test_model_service
node --test
```

The HTTP integration test starts the real Node connector and Python model service
with a fake model scorer. It verifies transport and failure handling, not model
accuracy, LiveKit credentials, telephony routing, or a real phone call.

