# JEV transcript connector

This backend accepts a text transcript and forwards it to the JEV model service. It returns only the model's scam probability. A caller may send a new full transcript every 2–3 seconds; each request is independent. There is no phone app, transcript capture, session state, risk engine, or alert logic in this component.

```text
Transcript producer -> POST /v1/jev/probability -> JEV model service
                                           <- { "probability": 0.82 }
```

## Run

Use Node 22 or later. Start the trained JEV model as a separate HTTP service, then point the connector to its prediction endpoint:

```powershell
cd 'backend/Transcript-Based Detector'
$env:JEV_MODEL_URL='http://127.0.0.1:8000/predict'
npm start
```

The post-trained call model is downloaded separately using `python3 ios/scripts/setup_posttrained_jev.py` from the repository root. Install `requirements-model.txt` and run `python3 model_service.py` to serve its caller-only V2 ONNX bundle at `http://127.0.0.1:8000/predict`. The service verifies the published bundle hashes and uses the same prompt, last 300 context tokens, and calibration as the iOS call classifier. See `../AI Deepfake Pipeline/LiveKit Setup/INCOMING_CALL_SETUP.md` for the complete LiveKit/Vosk path.

Without `JEV_MODEL_URL`, the connector returns HTTP 503 rather than inventing a probability. To check the connector without the trained model, run `npm test`. The test starts a fake JEV service and verifies the full HTTP path. `python3 -m unittest -v test_model_service` additionally checks the real connector through the Python service with fake model inference. These tests do not validate model accuracy.

## API contract

Call `POST http://localhost:3000/v1/jev/probability` with JSON:

```json
{ "transcript": "The latest full transcript" }
```

Successful response:

```json
{ "probability": 0.82 }
```

The configured JEV service receives the same JSON body and must respond with JSON containing a finite `probability` from 0 to 1. It has 2.5 seconds to respond. Invalid transcript input returns HTTP 400; an unconfigured or unavailable model returns HTTP 503. `GET /health` reports whether `JEV_MODEL_URL` is configured. Transcripts are limited to 20,000 characters and are not persisted or logged by this connector.

Point `JEV_MODEL_URL` at the model service's HTTP prediction endpoint. The connector is tested against that contract. The post-trained model remains experimental, with synthetic-data calibration and no established real-call/prefix accuracy.

## Recorded-call research candidates

The October 20 research pass adds script-disjoint FTC/NCSU transcripts, speaker-disjoint Switchboard conversation text, external recorded banking roleplay, and six public-audio/Vosk probes. See [the evaluation report](../../docs/testing/2026-10-20-transcript/REPORT.md) and [method/source notes](../../docs/testing/2026-10-20-transcript/RESEARCH.md). These are small development comparisons, not a 99% deployment claim. New research checkpoints are local, ignored artifacts; they are not part of the V1/V2 release or deployed cloud service.

The adapter keeps the existing `/predict` success contract and adds `POST /assess` for explicit score metadata: `scoreType`, `modelVersion`, `modelSha256`, `calibratedOnRealCalls: false`, `contextMode`, `windows`, and `contextCovered`. Caller-authored classifier control tokens are stripped. A greeting with fewer than four meaningful words returns HTTP 422 with `decision: insufficient_evidence`, rather than a false low-risk score. The existing Node connector maps unsuccessful upstream requests to HTTP 503; the streaming producer preserves an unavailable/listening state rather than interpreting it as safe.

Local candidate selection is explicit:

```sh
.venv/bin/python 'backend/Transcript-Based Detector/model_service.py' \
  --version V5 --model-dir backend/jev-posttrain/runs/call-v5-balanced \
  --bundle-manifest backend/jev-posttrain/runs/call-v5-balanced/bundle.json \
  --context-mode windows
```

Only run this after exporting and packaging that local candidate. Startup checks the ONNX, tokenizer, and temperature checksums together. The service binds to loopback. A model score never blocks or reports a caller, and cannot independently send a guardian message.

`--context-mode windows` is the suggested V5 development configuration based on the exploratory comparison, bounded to six overlapping windows with maximum-score pooling. It retains early evidence but can increase false alarms and has different calibration. The service's global default remains the last 300 context tokens (`tail`), matching the deployed V2 policy. Default version remains V2 until a candidate passes independent validation and the service is explicitly upgraded. This command alone does not update the iOS on-device model.

