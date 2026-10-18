"""Audio-only relay: Twilio Media Streams -> one authenticated iPhone.

Signaling backend creates the per-call subscription. Vosk/Jev remain on the phone.
No audio, transcripts, tokens, or URLs are logged or written to disk.
"""
import asyncio
from dataclasses import dataclass, field
import hmac
import json
import os
import re
import secrets
import time
import uuid
from aiohttp import web, WSMsgType
from twilio.request_validator import RequestValidator


@dataclass
class Subscription:
    call_sid: str
    track: str
    token: str
    expires: float
    ready: asyncio.Event = field(default_factory=asyncio.Event)
    phone: object = None
    twilio: object = None
    used_phone: bool = False
    used_twilio: bool = False


def create_app(*, admin_key, auth_token, public_origin):
    if not admin_key or not auth_token or not public_origin.startswith("https://"):
        raise ValueError("Set RELAY_ADMIN_KEY, TWILIO_AUTH_TOKEN and PUBLIC_ORIGIN=https://your-host")
    origin = public_origin.rstrip("/")
    if not re.fullmatch(r"https://[A-Za-z0-9.:-]+", origin):
        raise ValueError("PUBLIC_ORIGIN must be a canonical HTTPS origin without a path")
    subscriptions = {}
    validator = RequestValidator(auth_token)

    def authorized(request, expected):
        return hmac.compare_digest(request.headers.get("Authorization", ""), "Bearer " + expected)

    async def create(request):
        if not authorized(request, admin_key):
            raise web.HTTPUnauthorized()
        for key, sub in list(subscriptions.items()):
            if sub.expires < time.monotonic() and sub.phone is None and sub.twilio is None:
                subscriptions.pop(key, None)
        if len(subscriptions) >= 100:
            raise web.HTTPServiceUnavailable()
        try:
            body = await request.json()
            call_sid, track = body["call_sid"], body["caller_track"]
            if not isinstance(call_sid, str) or not re.fullmatch(r"CA[a-zA-Z0-9_]{1,64}", call_sid) or track not in ("inbound", "outbound"):
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            raise web.HTTPBadRequest(text="Expected call_sid and caller_track")
        session_id = str(uuid.uuid4())
        sub = Subscription(call_sid, track, secrets.token_urlsafe(32), time.monotonic() + 300)
        subscriptions[session_id] = sub
        return web.json_response({"session_id": session_id, "call_sid": call_sid, "caller_track": track,
                                  "audio_url": origin.replace("https://", "wss://", 1) + "/audio/" + session_id,
                                  "bearer_token": sub.token,
                                  "twilio_stream_url": origin.replace("https://", "wss://", 1) + "/twilio/" + session_id,
                                  "expires_in": 300}, headers={"Cache-Control": "no-store"})

    def subscription(request):
        sub = subscriptions.get(request.match_info["session_id"])
        if sub is None or sub.expires < time.monotonic():
            raise web.HTTPNotFound()
        return sub

    async def phone(request):
        sub = subscription(request)
        if not authorized(request, sub.token):
            raise web.HTTPUnauthorized()
        if sub.used_phone:
            raise web.HTTPConflict()
        sub.used_phone = True  # No await between checking and claiming.
        ws = web.WebSocketResponse(max_msg_size=64_000, heartbeat=20)
        try:
            await ws.prepare(request)
            sub.phone = ws
            sub.ready.set()
            async for _ in ws:  # Subscriber cannot inject audio back into a call.
                await ws.close(code=1008, message=b"Read-only audio subscription")
                break
        finally:
            sub.phone = None
            sub.ready.clear()
            if sub.twilio is not None:
                await sub.twilio.close()
            subscriptions.pop(request.match_info["session_id"], None)
        return ws

    async def twilio(request):
        # Validate against the configured PUBLIC origin, never a spoofable Host header.
        signature = request.headers.get("X-Twilio-Signature", "")
        signed_url = origin + request.raw_path
        if not signature or not any(validator.validate(url, {}, signature) for url in (signed_url, signed_url + "/")):
            raise web.HTTPUnauthorized()
        sub = subscription(request)
        if sub.used_twilio:
            raise web.HTTPConflict()
        sub.used_twilio = True
        ws = web.WebSocketResponse(max_msg_size=64_000, heartbeat=20)
        stream_sid = None
        try:
            await ws.prepare(request)
            sub.twilio = ws
            # Never buffer caller audio for a missing subscriber. Wait only for setup.
            await asyncio.wait_for(sub.ready.wait(), timeout=15)
            sub.expires = time.monotonic() + 3600  # Bound live subscriptions to one hour.
            async for message in ws:
                if message.type != WSMsgType.TEXT:
                    break
                body = json.loads(message.data)
                if not isinstance(body, dict):
                    raise ValueError("Expected a stream object")
                event = body.get("event")
                if event == "connected":
                    pass
                elif event == "start":
                    start = body["start"]
                    fmt = start["mediaFormat"]
                    if stream_sid is not None or start["callSid"] != sub.call_sid or sub.track not in start["tracks"] or fmt != {"encoding": "audio/x-mulaw", "sampleRate": 8000, "channels": 1}:
                        raise ValueError("Invalid stream start")
                    stream_sid = start["streamSid"]
                    if not stream_sid or body["streamSid"] != stream_sid:
                        raise ValueError("Invalid stream identity")
                elif event in ("media", "stop"):
                    if stream_sid is None or body["streamSid"] != stream_sid:
                        raise ValueError("Invalid stream identity")
                    if event == "media" and body["media"]["track"] != sub.track:
                        continue
                else:
                    raise ValueError("Unexpected stream event")
                if sub.phone is None:
                    break
                # Await the write: a slow device never creates an unbounded audio queue.
                await asyncio.wait_for(sub.phone.send_str(message.data), timeout=5)
                if event == "stop":
                    break
        except (TimeoutError, ValueError, KeyError, TypeError, ConnectionError):
            pass
        finally:
            sub.twilio = None
            if sub.phone is not None:
                await sub.phone.close()
            await ws.close()
            subscriptions.pop(request.match_info["session_id"], None)
        return ws

    async def cleanup(app):
        while True:
            await asyncio.sleep(10)
            for key, sub in list(subscriptions.items()):
                if sub.expires < time.monotonic():
                    if sub.phone is not None:
                        await sub.phone.close()
                    if sub.twilio is not None:
                        await sub.twilio.close()
                    subscriptions.pop(key, None)

    async def lifespan(app):
        worker = asyncio.create_task(cleanup(app))
        yield
        worker.cancel()
        try:
            await worker
        except asyncio.CancelledError:
            pass
        for sub in list(subscriptions.values()):
            if sub.phone is not None:
                await sub.phone.close()
            if sub.twilio is not None:
                await sub.twilio.close()

    app = web.Application(client_max_size=4096)
    app.router.add_post("/sessions", create)
    app.router.add_get("/audio/{session_id}", phone)
    app.router.add_get("/twilio/{session_id}", twilio)
    app.cleanup_ctx.append(lifespan)
    return app


if __name__ == "__main__":
    web.run_app(create_app(admin_key=os.environ["RELAY_ADMIN_KEY"], auth_token=os.environ["TWILIO_AUTH_TOKEN"],
                           public_origin=os.environ["PUBLIC_ORIGIN"]),
                host=os.environ.get("RELAY_HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "8765")), access_log=None)
