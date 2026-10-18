# Call Shield caller-audio relay

This is an audio-only bridge between Twilio Media Streams and the iPhone's local transcript pipeline. It does not place calls, issue Twilio Voice access tokens, or replace Shrey's calling server. The server integration contract is in `ios/PIPELINE2_TWILIO_HANDOFF.md`.

## Run behind public TLS

```sh
python3 -m venv .venv-relay
.venv-relay/bin/pip install -r requirements.txt
export PUBLIC_ORIGIN=https://your-relay-host
export RELAY_ADMIN_KEY='<strong server-to-server secret>'
export TWILIO_AUTH_TOKEN='<Twilio account auth token, server only>'
.venv-relay/bin/python relay.py
```

The process listens on 127.0.0.1:8765 by default. Configure a TLS reverse proxy/tunnel to that address. Set `PORT` or `RELAY_HOST` if needed. Keep `PUBLIC_ORIGIN` exactly aligned with Twilio's public URL, including ports where relevant. Handshake validation follows [Twilio's signature guidance](https://www.twilio.com/docs/usage/security), including the documented trailing-slash alternative. HTTP requests and credentials are not access-logged by this service; configure the reverse proxy's logs appropriately too.

Your authenticated signaling server calls:

```http
POST /sessions
Authorization: Bearer <RELAY_ADMIN_KEY>
Content-Type: application/json

{"call_sid":"CA_actual_streamed_leg","caller_track":"inbound"}
```

The response contains `session_id`, `audio_url`, `bearer_token`, `twilio_stream_url`, `caller_track`, `call_sid` and `expires_in`. Only the per-call audio URL/token goes to the app. The Twilio handshake at `/twilio/<session_id>` requires the genuine `X-Twilio-Signature`. The app subscriber at `/audio/<session_id>` requires its per-call bearer token. The server owns authorization of which call leg belongs to which user before it creates the subscription. Neither path accepts arbitrary transcript input.

Create the subscription after the SDK call connects. Tell the phone to subscribe, then start the caller leg's unidirectional Twilio Media Stream. The relay waits up to 15 seconds for the subscriber without buffering speech. Call SID, Stream SID and media format must match. Only one phone and one Twilio stream may use each subscription. Invalid streams and disconnects close the paired connection. Do not reconnect an expired subscription; create a new one and reset the app's analysis session.

State is held in one process and disappears on restart. Maximum 100 subscriptions, 64 KB messages, five-minute setup expiry and one-hour active cap. This prototype needs shared coordination or sticky routing before multi-worker deployment. No audio/transcript is stored; the server sees the audio in transit, so the design is not fully offline.

## Tests

```sh
.venv-relay/bin/python -m unittest -v test_relay.py
```

For the opt-in native simulator WebSocket integration test, start a separate **loopback-only** relay using these deliberately non-production test credentials:

```sh
RELAY_ADMIN_KEY=test-admin TWILIO_AUTH_TOKEN=test-twilio-token \
PUBLIC_ORIGIN=https://relay.example .venv-relay/bin/python relay.py
```

Then run `TranscriptPipelineTests/testAuthenticatedWebSocketRelayToLocalJev` in Xcode. Its simulated Twilio producer signs its request and sends actual synthetic speech in 20-ms 8 kHz mu-law chunks. It runs Jev in the simulator, not in Python. The test skips with an explicit message if the local relay is unavailable; ordinary audio/model tests need no relay. Release app subscriptions require `wss`; only Debug permits `ws` to a loopback host.
