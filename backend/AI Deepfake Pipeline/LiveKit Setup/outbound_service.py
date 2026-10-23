"""Single-recipient outbound gateway. Run behind HTTPS; credentials stay server-side.

Requires LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET, CALLMA_OUTBOUND_TRUNK_ID,
CALLMA_OUTBOUND_ALLOWED_NUMBERS (comma-separated E.164 test destinations).
Authenticates the existing signed senior lobby token. Never expose an unrestricted dialer.
"""
import asyncio
import os
import re
import time
import uuid
from datetime import timedelta

from aiohttp import web
from livekit import api
from google.protobuf.duration_pb2 import Duration
import jwt
from senior_ring import mint_call_token, SENIOR_IDENTITY, SENIOR_LOBBY_ROOM


def create_app(lk, key, secret, trunk, allowed):
    calls = {}
    recent = []
    tasks = set()

    def authenticate(request):
        token = request.headers.get('Authorization', '').removeprefix('Bearer ')
        try:
            claims = jwt.decode(token, secret, algorithms=['HS256'], issuer=key,
                                options={'require': ['exp', 'iss', 'sub']})
            grants = claims.get('video', {})
            if claims['sub'] != SENIOR_IDENTITY or grants.get('room') != SENIOR_LOBBY_ROOM or not grants.get('roomJoin'):
                raise ValueError()
        except Exception:
            raise web.HTTPUnauthorized(text='Calling access was refused.')

    async def delete_room(room):
        try:
            await asyncio.wait_for(lk.room.delete_room(api.DeleteRoomRequest(room=room)), 10)
        except Exception:
            pass  # The room may already have been removed by LiveKit.

    async def supervise(room):
        # Disconnect the SIP leg if the app never joins, leaves, or exceeds two hours.
        joined = False
        deadline = time.monotonic() + 7200
        join_deadline = time.monotonic() + 20
        try:
            while time.monotonic() < deadline:
                result = await lk.room.list_participants(api.ListParticipantsRequest(room=room))
                present = any(p.identity == SENIOR_IDENTITY for p in result.participants)
                if present:
                    joined = True
                elif joined or time.monotonic() > join_deadline:
                    return
                await asyncio.sleep(2)
        finally:
            await delete_room(room)

    async def call(request):
        authenticate(request)
        try:
            call_id = str(uuid.UUID(request.match_info['id']))
        except ValueError:
            raise web.HTTPBadRequest()
        room = 'callma-out-' + call_id
        if request.method == 'DELETE':
            record = calls.setdefault(call_id, {'cancelled': True})
            record['cancelled'] = True
            if record.get('task'):
                record['task'].cancel()
            await delete_room(room)
            return web.json_response({'ended': True})
        if call_id in calls:
            raise web.HTTPConflict(text='This call request has already been used.')
        # Bound memory and prevent repeated billed dialing attempts.
        if len(calls) >= 10000:
            raise web.HTTPServiceUnavailable(text='Calling service needs maintenance.')
        now = time.monotonic()
        recent[:] = [t for t in recent if now - t < 60]
        if len(recent) >= 3 or any(v.get('active') for v in calls.values()):
            raise web.HTTPTooManyRequests(text='Another call is active or the calling limit was reached.')
        try:
            payload = await request.json()
            number = payload['number']
            if not isinstance(number, str) or not re.fullmatch(r'\+[1-9][0-9]{7,14}', number) or number not in allowed:
                raise ValueError()
        except Exception:
            raise web.HTTPBadRequest(text='This destination is not enabled for calling.')
        # request.json() yields: recheck before accepting the billed operation.
        if call_id in calls or any(v.get('active') for v in calls.values()):
            raise web.HTTPConflict()
        recent.append(now)
        record = calls[call_id] = {'active': True, 'cancelled': False, 'task': asyncio.current_task()}
        identity = 'outbound-' + call_id
        handed_off = False
        try:
            await lk.room.create_room(api.CreateRoomRequest(name=room, empty_timeout=30))
            await lk.agent_dispatch.create_dispatch(api.CreateAgentDispatchRequest(
                room=room, agent_name='scam-guard', metadata='callma-outbound-v1'))
            await asyncio.wait_for(lk.sip.create_sip_participant(api.CreateSIPParticipantRequest(
                sip_trunk_id=trunk, sip_call_to=number, room_name=room,
                participant_identity=identity, wait_until_answered=True,
                ringing_timeout=Duration(seconds=30), max_call_duration=Duration(seconds=7200))), 65)
            if record['cancelled']:
                raise asyncio.CancelledError()
            token = mint_call_token(room, api_key=key, api_secret=secret)
            task = asyncio.create_task(supervise(room))
            tasks.add(task)
            task.add_done_callback(tasks.discard)
            task.add_done_callback(lambda _: record.update(active=False))
            handed_off = True
            return web.json_response({'type': 'incoming_call', 'callUUID': call_id,
                'room': room, 'token': token, 'handle': number, 'callerIdentity': identity})
        except asyncio.CancelledError:
            raise
        except Exception:
            raise web.HTTPBadGateway(text='The outgoing call could not connect. Check the trunk and destination.')
        finally:
            record['task'] = None
            if not handed_off:
                record['active'] = False
                await delete_room(room)

    async def cleanup(app):
        for task in list(tasks):
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await lk.aclose()

    app = web.Application(client_max_size=4096)
    app.router.add_post('/calls/{id}', call)
    app.router.add_delete('/calls/{id}', call)
    app.on_cleanup.append(cleanup)
    return app


if __name__ == '__main__':
    key = os.environ['LIVEKIT_API_KEY']
    secret = os.environ['LIVEKIT_API_SECRET']
    trunk = os.environ['CALLMA_OUTBOUND_TRUNK_ID']
    allowed = set(filter(None, os.environ['CALLMA_OUTBOUND_ALLOWED_NUMBERS'].split(',')))
    async def app():
        return create_app(api.LiveKitAPI(), key, secret, trunk, allowed)
    web.run_app(app(), host='127.0.0.1', port=8020, access_log=None)
