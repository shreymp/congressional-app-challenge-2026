"""Gateway contract tests with fake LiveKit APIs; no phone calls or network service."""
import asyncio
import time
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import jwt
from aiohttp.test_utils import TestClient, TestServer
from outbound_service import create_app
from senior_ring import SENIOR_IDENTITY, SENIOR_LOBBY_ROOM


class GatewayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.key, self.secret = 'test-key', 'a' * 40
        self.lk = SimpleNamespace(
            room=SimpleNamespace(create_room=AsyncMock(), delete_room=AsyncMock(),
                list_participants=AsyncMock(return_value=SimpleNamespace(participants=[]))),
            sip=SimpleNamespace(create_sip_participant=AsyncMock()),
            agent_dispatch=SimpleNamespace(create_dispatch=AsyncMock()), aclose=AsyncMock())
        token = jwt.encode({'iss': self.key, 'sub': SENIOR_IDENTITY, 'exp': int(time.time()) + 60,
                            'video': {'roomJoin': True, 'room': SENIOR_LOBBY_ROOM}}, self.secret, algorithm='HS256')
        self.headers = {'Authorization': 'Bearer ' + token}
        self.client = TestClient(TestServer(create_app(self.lk, self.key, self.secret, 'trunk-test', {'+13125550123'})))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()

    async def test_denies_unauthenticated_and_unapproved_destination(self):
        path = '/calls/' + str(uuid.uuid4())
        response = await self.client.post(path, json={'number': '+13125550123'})
        self.assertEqual(response.status, 401)
        response = await self.client.post(path, headers=self.headers, json={'number': '+442055501234'})
        self.assertEqual(response.status, 400)
        self.lk.sip.create_sip_participant.assert_not_called()

    async def test_answered_call_uses_trunk_and_returns_room_token(self):
        call_id = str(uuid.uuid4())
        response = await self.client.post('/calls/' + call_id, headers=self.headers, json={'number': '+13125550123'})
        self.assertEqual(response.status, 200)
        invite = await response.json()
        self.assertEqual(invite['callUUID'], call_id)
        request = self.lk.sip.create_sip_participant.call_args.args[0]
        self.assertEqual(request.sip_trunk_id, 'trunk-test')
        self.assertTrue(request.wait_until_answered)
        claims = jwt.decode(invite['token'], self.secret, algorithms=['HS256'], issuer=self.key)
        self.assertEqual(claims['video']['room'], invite['room'])
        duplicate = await self.client.post('/calls/' + call_id, headers=self.headers, json={'number': '+13125550123'})
        self.assertEqual(duplicate.status, 409)

    async def test_cancel_before_start_prevents_dial(self):
        path = '/calls/' + str(uuid.uuid4())
        self.assertEqual((await self.client.delete(path, headers=self.headers)).status, 200)
        self.assertEqual((await self.client.post(path, headers=self.headers, json={'number': '+13125550123'})).status, 409)
        self.lk.sip.create_sip_participant.assert_not_called()

    async def test_provider_failure_deletes_room(self):
        self.lk.sip.create_sip_participant.side_effect = RuntimeError('provider rejected')
        response = await self.client.post('/calls/' + str(uuid.uuid4()), headers=self.headers, json={'number': '+13125550123'})
        self.assertEqual(response.status, 502)
        self.lk.room.delete_room.assert_awaited()
