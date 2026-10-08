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

The trained model is not in this repository yet. Without `JEV_MODEL_URL`, the connector returns HTTP 503 rather than inventing a probability. To check the connector without the trained model, run `npm test`. The test starts a fake JEV service and verifies the full HTTP path.

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

When the trained model is ready, point `JEV_MODEL_URL` at its HTTP prediction endpoint. The connector is tested against that contract, not the trained model itself.
