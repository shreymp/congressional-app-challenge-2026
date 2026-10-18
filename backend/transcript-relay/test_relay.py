import unittest
from aiohttp import WSMsgType, WSServerHandshakeError
from aiohttp.test_utils import AioHTTPTestCase
from twilio.request_validator import RequestValidator
from relay import create_app


class RelayTests(AioHTTPTestCase):
    async def get_application(self):
        return create_app(admin_key="test-admin", auth_token="test-twilio-token", public_origin="https://relay.example")

    async def subscribe(self):
        response = await self.client.post("/sessions", json={"call_sid": "CA_test", "caller_track": "inbound"},
                                          headers={"Authorization": "Bearer test-admin"})
        self.assertEqual(response.status, 200)
        return await response.json()

    def signed(self, sid):
        signature = RequestValidator("test-twilio-token").compute_signature("https://relay.example/twilio/" + sid, {})
        return {"X-Twilio-Signature": signature}

    async def test_requires_admin_signature_and_per_call_phone_token(self):
        response = await self.client.post("/sessions", json={"call_sid": "CA_test", "caller_track": "inbound"})
        self.assertEqual(response.status, 401)
        sub = await self.subscribe()
        sid = sub["session_id"]
        with self.assertRaises(WSServerHandshakeError) as denied:
            await self.client.ws_connect("/audio/" + sid)
        self.assertEqual(denied.exception.status, 401)
        with self.assertRaises(WSServerHandshakeError) as denied:
            await self.client.ws_connect("/twilio/" + sid)
        self.assertEqual(denied.exception.status, 401)
        other = await self.subscribe()
        with self.assertRaises(WSServerHandshakeError):
            await self.client.ws_connect("/audio/" + other["session_id"], headers={"Authorization": "Bearer " + sub["bearer_token"]})

    async def test_signed_twilio_forwards_only_bound_caller_and_cleans_up(self):
        sub = await self.subscribe()
        sid = sub["session_id"]
        phone = await self.client.ws_connect("/audio/" + sid, headers={"Authorization": "Bearer " + sub["bearer_token"]})
        twilio = await self.client.ws_connect("/twilio/" + sid, headers=self.signed(sid))
        start = {"event": "start", "streamSid": "MZ_test", "start": {"streamSid": "MZ_test", "callSid": "CA_test", "tracks": ["inbound", "outbound"],
                 "mediaFormat": {"encoding": "audio/x-mulaw", "sampleRate": 8000, "channels": 1}}}
        await twilio.send_json(start)
        self.assertEqual(await phone.receive_json(timeout=2), start)
        await twilio.send_json({"event": "media", "streamSid": "MZ_test", "media": {"track": "outbound", "chunk": "1", "payload": "fw=="}})
        caller = {"event": "media", "streamSid": "MZ_test", "media": {"track": "inbound", "chunk": "1", "payload": "/w=="}}
        await twilio.send_json(caller)
        self.assertEqual(await phone.receive_json(timeout=2), caller)
        stop = {"event": "stop", "streamSid": "MZ_test"}
        await twilio.send_json(stop)
        self.assertEqual(await phone.receive_json(timeout=2), stop)
        self.assertEqual((await phone.receive(timeout=2)).type, WSMsgType.CLOSE)
        await phone.close(); await twilio.close()
        with self.assertRaises(WSServerHandshakeError):
            await self.client.ws_connect("/audio/" + sid, headers={"Authorization": "Bearer " + sub["bearer_token"]})

    async def test_wrong_call_identity_and_duplicate_subscribers_are_rejected(self):
        sub = await self.subscribe()
        sid = sub["session_id"]
        headers = {"Authorization": "Bearer " + sub["bearer_token"]}
        phone = await self.client.ws_connect("/audio/" + sid, headers=headers)
        with self.assertRaises(WSServerHandshakeError) as denied:
            await self.client.ws_connect("/audio/" + sid, headers=headers)
        self.assertEqual(denied.exception.status, 409)
        twilio = await self.client.ws_connect("/twilio/" + sid, headers=self.signed(sid))
        await twilio.send_json({"event": "start", "streamSid": "MZ_test", "start": {"streamSid": "MZ_test", "callSid": "CA_other", "tracks": ["inbound"],
                             "mediaFormat": {"encoding": "audio/x-mulaw", "sampleRate": 8000, "channels": 1}}})
        self.assertEqual((await phone.receive(timeout=2)).type, WSMsgType.CLOSE)
        await phone.close(); await twilio.close()


if __name__ == "__main__":
    unittest.main()
