# Outgoing LiveKit calls

The iOS keypad can now use a separate HTTPS gateway instead of handing calls to the mobile service. The gateway creates a room, dispatches `scam-guard`, dials an outbound SIP participant, waits for answer, and returns a short-lived room token. The app joins and publishes its microphone; its connected timer waits for audio activation. The agent's outbound job skips the incoming ring supervisor and continues scoring the remote SIP participant.

This is an implemented integration, not a verified live telephone service. This checkout has no outbound SIP trunk or server API secret configured. A LiveKit inbound phone number alone cannot originate these calls.

## Server setup

1. Configure an outbound SIP trunk with a supported telephone provider and LiveKit. Use the provider-authorized caller ID. See [LiveKit outbound trunks](https://docs.livekit.io/telephony/making-calls/outbound-trunk/).
2. Deploy this directory's updated `scam-guard` agent so it recognizes `callma-outbound-v1` job metadata.
3. Install `requirements.txt` on the calling server. Configure these environment variables there:
   - `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`: the same project as the iPhone's lobby token.
   - `CALLMA_OUTBOUND_TRUNK_ID`: the configured outbound trunk ID.
   - `CALLMA_OUTBOUND_ALLOWED_NUMBERS`: comma-separated E.164 test destinations, such as `+13125550123`. Other destinations are rejected. Do not enable arbitrary billed destinations without account/billing controls.
   - `SENIOR_IDENTITY` and `SENIOR_LOBBY_ROOM` if different from the existing defaults.
4. Run `python outbound_service.py`. It binds to loopback port 8020. Expose it through an HTTPS reverse proxy, with a request timeout longer than 75 seconds and request/access body logging disabled. Use one gateway process for this single-user pilot; its cancellation, rate-limit and idempotency state is in memory.
5. In the app's Settings → Configure Connection, keep the host/lobby token and enter the gateway's HTTPS base URL in **Outgoing LiveKit calls**. Save. Use the same setup on iPhone and Simulator.

The phone authenticates using its signed lobby token. API keys, API secrets and trunk credentials stay on the server. Calls are restricted to the one configured recipient identity, approved destination list, one active call, and three starts per minute. The LiveKit SIP leg has a 30-second ringing timeout and two-hour maximum duration. Caller ID and emergency-service support must come from the phone provider; this pilot is not an emergency dialer or complete carrier replacement.

## Lifecycle and limits

POST `/calls/{UUID}` with `{"number":"+13125550123"}` waits for remote answer, then returns the room invite. Reusing a UUID is rejected. DELETE with the same UUID cancels it and deletes its room. The app ends the phone leg on cancellation, errors and local teardown. Server supervision deletes the room if the phone fails to join within 20 seconds after answer, leaves, or reaches the maximum duration. There may be a short silent interval after remote answer while the app joins. No local ringback tone is implemented.

The gateway does not provide voicemail, background incoming push, account signup, general multi-user routing or durable recovery after process restart. The existing inbound foreground listener remains unchanged. Service health is not confirmed merely by saving a URL.

## Verification

- Four isolated gateway tests passed using fake LiveKit APIs: authentication/destination rejection, outbound trunk/token contract, cancel-before-start, and provider-error cleanup. No telephone network was contacted.
- The existing 65 native tests passed after outbound changes; simulator build passed.
- A real outgoing call, answer delay, detector-agent behavior on an outgoing SIP leg, lock-screen audio activation and physical iPhone routes still require an actual provisioned trunk and device validation.
