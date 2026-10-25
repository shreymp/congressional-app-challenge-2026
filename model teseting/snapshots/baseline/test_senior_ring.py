"""Offline test of senior_ring.py: drives the ring state machine with fakes. No LiveKit, no network.

  python test_senior_ring.py

A plain script (pytest is not needed). The timings are shortened through SeniorRing's
parameters, so the whole run takes a few seconds. Exits with code 1 if any check fails.
"""
import asyncio
import json
import logging
import os
import subprocess
import sys
import time
import types
import uuid

import jwt
from livekit import api, rtc
from livekit.agents import JobContext

import senior_ring
from senior_ring import CALLER_LEFT, CRASHED, SENIOR_HUNG_UP

KEY, SECRET = "APIdevkey", "dev-secret-only-used-by-this-offline-test"   # dummy, never sent anywhere
SENIOR, LOBBY = senior_ring.SENIOR_IDENTITY, senior_ring.SENIOR_LOBBY_ROOM
CALLER, NUMBER = "sip_+15551234567", "+15551234567"
MIC = rtc.TrackSource.SOURCE_MICROPHONE
SIP = rtc.ParticipantKind.PARTICIPANT_KIND_SIP
STANDARD = rtc.ParticipantKind.PARTICIPANT_KIND_STANDARD
CONTRACT_KEYS = {"type", "callUUID", "room", "token", "handle", "callerIdentity"}

# Short timings. Windows timers tick every ~16 ms, so nothing here is tighter than that.
FAST = dict(ring_timeout=0.6, resend_every=0.05, left_grace=0.2, poll_every=0.01, api_timeout=0.3)
SETTLE = 0.08


def mint(room_name: str) -> str:
    return senior_ring.mint_call_token(room_name, api_key=KEY, api_secret=SECRET)


# ---------------------------------------------------------------- fakes

class Pub:
    def __init__(self, source):
        self.source = source


class Person:
    def __init__(self, identity, kind=STANDARD, attributes=None, mic=False):
        self.identity, self.kind, self.attributes = identity, kind, dict(attributes or {})
        self.track_publications = {"TR_mic": Pub(MIC)} if mic else {}


class FakeRoom:
    """The parts of rtc.Room the ring uses."""

    def __init__(self, people=(), name="call-_+15551234567_AbCdEf"):
        self.name, self.connected = name, True
        self.remote_participants = {p.identity: p for p in people}
        self.handlers = {}

    def isconnected(self):
        return self.connected

    def on(self, event, callback):
        self.handlers.setdefault(event, []).append(callback)

    def join(self, person):            # like rtc.Room: add first, then emit participant_connected
        self.remote_participants[person.identity] = person
        for cb in self.handlers.get("participant_connected", []):
            cb(person)

    def leave(self, identity):
        self.remote_participants.pop(identity, None)


class FakeRoomService:
    """lobby: identities connected to the lobby room, or None if that room does not exist."""

    def __init__(self, lobby):
        self.lobby, self.sent, self.list_calls = lobby, [], 0
        self.fail, self.hang = None, False

    async def list_participants(self, req):
        self.list_calls += 1
        if self.hang:
            await asyncio.Event().wait()
        if self.fail == "list":
            raise RuntimeError("list_participants boom")
        if self.lobby is None:
            raise api.TwirpError(api.TwirpErrorCode.NOT_FOUND, "requested room does not exist", status=404)
        assert req.room == LOBBY, req.room
        return api.ListParticipantsResponse(participants=[api.ParticipantInfo(identity=i) for i in self.lobby])

    async def send_data(self, req):
        if self.fail == "send":
            raise RuntimeError("send_data boom")
        self.sent.append(req)
        return api.SendDataResponse()


class FakeLK:
    def __init__(self, lobby):
        self.room = FakeRoomService(lobby)


class Call:
    """One fake phone call: the caller is in the room and a SeniorRing runs with short timings."""

    def __init__(self, *, lobby=(SENIOR,), **overrides):
        # A real phone caller publishes its own audio while it is still ringing.
        self.room = FakeRoom([Person(CALLER, SIP, {"sip.callStatus": "ringing",
                                                    "sip.phoneNumber": NUMBER}, mic=True)])
        self.lk = FakeLK(None if lobby is None else list(lobby))
        self.fallbacks, self.deletes = [], 0
        self.delete_fails, self.delete_hangs = False, False
        opts = dict(FAST, mint_token=mint, no_answer=self._no_answer)
        opts.update(overrides)
        self.ring = senior_ring.SeniorRing(lk=self.lk, room=self.room, caller_identity=CALLER,
                                           handle=NUMBER, delete_room=self._delete_room, **opts)
        self.task = asyncio.create_task(self.ring.run())

    async def _delete_room(self):
        self.deletes += 1
        if self.delete_hangs:                # the server never answers
            await asyncio.Event().wait()
        if self.delete_fails:
            # Like JobContext.delete_room: it logs the API error and does not raise, so the only
            # sign of a failed delete is that the room (and the agent in it) stays connected.
            return
        self.room.connected = False          # deleting a room disconnects everyone, the agent too

    def _no_answer(self, **kw):
        self.fallbacks.append(kw)

    @property
    def sent(self):
        return self.lk.room.sent

    def invites(self):
        return [json.loads(r.data.decode("utf-8")) for r in self.sent]

    def senior_joins(self, mic=False):
        self.room.join(Person(SENIOR, mic=mic))

    def senior_answers(self):
        self.room.remote_participants[SENIOR].track_publications["TR_senior_mic"] = Pub(MIC)

    async def finish(self, timeout=3.0):
        return await asyncio.wait_for(self.task, timeout)

    async def close(self):
        self.task.cancel()
        await asyncio.gather(self.task, return_exceptions=True)


async def until(cond, what, timeout=3.0):
    end = time.monotonic() + timeout
    while not cond():
        assert time.monotonic() < end, f"timed out waiting for: {what}"
        await asyncio.sleep(0.005)


def claims(token: str) -> dict:
    return jwt.decode(token, SECRET, algorithms=["HS256"])


# ---------------------------------------------------------------- tests

async def test_invite_has_exactly_the_contract_keys():
    inv = senior_ring.build_invite(call_uuid=str(uuid.uuid4()), room_name="call-x", token="tok",
                                   handle="", caller_identity=CALLER)
    assert set(inv) == CONTRACT_KEYS, inv
    assert inv["type"] == "incoming_call" and inv["handle"] == "" and inv["callerIdentity"] == CALLER
    assert all(isinstance(v, str) for v in inv.values())
    named = senior_ring.build_invite(call_uuid="u", room_name="r", token="t", handle=None,
                                     caller_identity=CALLER, caller_name="Dr. Lee")
    assert set(named) == CONTRACT_KEYS | {"callerName"} and named["handle"] == ""
    assert senior_ring.INCOMING_TOPIC == "callshield.incoming"


async def test_call_token_grants():
    c = claims(mint("call-_+15551234567_AbCdEf"))
    assert c["sub"] == SENIOR and c["iss"] == KEY, c
    v = c["video"]
    assert v["room"] == "call-_+15551234567_AbCdEf" and v["roomJoin"] is True, v
    assert v["canSubscribe"] is True and v["canPublish"] is True, v
    assert v["canPublishSources"] == ["microphone"] and v["canPublishData"] is False, v
    assert not any(v.get(k) for k in ("roomAdmin", "roomCreate", "roomList", "hidden")), v
    ttl = c["exp"] - c["nbf"]
    assert ttl == senior_ring.CALL_TOKEN_TTL_SEC, c
    # Late re-sends carry this token. LiveKit Cloud's token refresh behaviour is not public, so the
    # lifetime keeps a margin of several minutes over the ring window.
    assert ttl >= senior_ring.RING_TIMEOUT_SEC + 5 * 60 + 60, "must keep a margin over the ring window"
    assert ttl >= 600
    assert ttl <= 960, "the call token is meant to be short-lived (max RING_TIMEOUT_SEC 600 + 6 min)"


async def test_lobby_token_grants():
    c = claims(senior_ring.mint_lobby_token(ttl_days=30, api_key=KEY, api_secret=SECRET))
    v = c["video"]
    assert c["sub"] == SENIOR and v["room"] == LOBBY and v["roomJoin"] is True, c
    assert v["canPublish"] is False and v["canPublishData"] is False and v["canSubscribe"] is True, v
    assert c["exp"] - c["nbf"] == 30 * 24 * 3600, c


async def test_invite_is_resent_until_the_senior_joins():
    call = Call()
    await until(lambda: len(call.sent) >= 3, "three invites")
    for req in call.sent:
        assert req.room == LOBBY and req.topic == "callshield.incoming"
        assert list(req.destination_identities) == [SENIOR] and not req.destination_sids
        assert req.kind == api.DataPacket.Kind.RELIABLE
        assert req.nonce == b""            # RoomService.send_data sets it; the ring must not
    invites = call.invites()
    assert all(i == invites[0] for i in invites), "re-sends must be identical (same callUUID)"
    inv = invites[0]
    assert set(inv) == CONTRACT_KEYS, inv
    assert uuid.UUID(inv["callUUID"]).version == 4 and inv["callUUID"] == call.ring.call_uuid
    assert inv["type"] == "incoming_call" and inv["room"] == call.room.name
    assert inv["handle"] == NUMBER and inv["callerIdentity"] == CALLER
    assert claims(inv["token"])["video"]["room"] == call.room.name

    call.senior_joins()                    # silently: no microphone yet
    await asyncio.sleep(SETTLE)
    n = len(call.sent)
    await asyncio.sleep(6 * FAST["resend_every"])
    assert len(call.sent) == n, "invites must stop once the senior is in the call room"
    assert call.ring.joined and not call.ring.answered
    await call.close()


async def test_no_invite_while_the_app_is_not_in_the_lobby():
    call = Call(lobby=None, ring_timeout=5)          # lobby room does not exist
    await until(lambda: call.lk.room.list_calls >= 3, "lobby checks")
    assert not call.sent
    call.lk.room.lobby = ["someone-else"]            # room exists, senior is not in it
    await asyncio.sleep(4 * FAST["resend_every"])
    assert not call.sent
    call.lk.room.lobby = ["someone-else", SENIOR]    # the app was opened
    await until(lambda: len(call.sent) >= 1, "invite after the app connected")
    await call.close()


async def test_timeout_fires_the_stub_exactly_once():
    t0 = time.monotonic()
    call = Call()
    await until(lambda: call.fallbacks, "no-answer stub")
    assert time.monotonic() - t0 >= 0.9 * FAST["ring_timeout"], "fired before the ring window ended"
    assert call.fallbacks[0] == {"room_name": call.room.name, "call_uuid": call.ring.call_uuid,
                                 "handle": NUMBER, "reason": "timeout"}, call.fallbacks
    await asyncio.sleep(SETTLE)
    n = len(call.sent)
    await asyncio.sleep(6 * FAST["resend_every"])
    assert len(call.sent) == n, "no invites after the ring window"
    assert len(call.fallbacks) == 1 and call.deletes == 0
    assert not call.task.done(), "the caller is still there: the ring must keep supervising"
    call.room.leave(CALLER)
    assert await call.finish() == CALLER_LEFT
    assert len(call.fallbacks) == 1 and call.deletes == 0


async def test_ringing_out_with_the_senior_in_the_room_fires_once():
    call = Call()
    await until(lambda: call.sent, "first invite")
    call.senior_joins()                    # CallKit is ringing; the caller's mic is published
    await until(lambda: call.fallbacks, "no-answer stub")
    assert call.fallbacks[0]["reason"] == "timeout"
    assert not call.ring.answered, "the CALLER's microphone must not count as an answer"
    call.room.leave(SENIOR)                # the phone's own ring timeout ends the CallKit call
    await asyncio.sleep(3 * FAST["left_grace"])
    assert len(call.fallbacks) == 1 and call.deletes == 0
    await call.close()


async def test_decline_fires_the_stub_exactly_once():
    call = Call(ring_timeout=1.2)
    await until(lambda: call.sent, "first invite")
    call.senior_joins()
    await asyncio.sleep(SETTLE)
    t_left = time.monotonic()
    call.room.leave(SENIOR)                # declined: the app leaves without publishing
    await until(lambda: call.fallbacks, "no-answer stub")
    assert time.monotonic() - t_left >= 0.9 * FAST["left_grace"], "fired before the grace period"
    assert time.monotonic() - t_left < 1.0, "should not have waited for the ring window"
    assert call.fallbacks[0]["reason"] == "declined"
    await asyncio.sleep(1.4)               # past the ring window: must not fire a second time
    assert len(call.fallbacks) == 1 and call.deletes == 0 and not call.task.done()
    call.room.leave(CALLER)
    assert await call.finish() == CALLER_LEFT
    assert len(call.fallbacks) == 1 and call.deletes == 0


async def test_blip_before_answering_is_not_a_decline():
    call = Call(ring_timeout=5)
    call.senior_joins()
    await asyncio.sleep(SETTLE)
    call.room.leave(SENIOR)
    await asyncio.sleep(FAST["left_grace"] / 4)
    call.senior_joins()                    # reconnected inside the grace period
    await asyncio.sleep(3 * FAST["left_grace"])
    assert not call.fallbacks and call.deletes == 0
    call.senior_answers()
    await until(lambda: call.ring.answered, "answered")
    await call.close()


async def test_hangup_after_answering_deletes_the_room():
    call = Call()
    await until(lambda: call.sent, "first invite")
    call.senior_joins()
    await asyncio.sleep(SETTLE)
    assert not call.ring.answered
    call.senior_answers()                  # microphone published = answered
    await until(lambda: call.ring.answered, "answered")
    await asyncio.sleep(FAST["ring_timeout"])        # an answered call has no ring timeout
    assert not call.fallbacks and call.deletes == 0
    t_left = time.monotonic()
    call.room.leave(SENIOR)
    await until(lambda: call.deletes, "delete_room")
    assert time.monotonic() - t_left >= 0.9 * FAST["left_grace"], "deleted before the grace period"
    assert await call.finish() == SENIOR_HUNG_UP
    assert call.deletes == 1 and not call.fallbacks


async def test_rejoin_within_grace_keeps_the_room():
    call = Call()
    call.senior_joins(mic=True)            # also: already answered when first seen
    await until(lambda: call.ring.answered, "answered")
    call.room.leave(SENIOR)
    await asyncio.sleep(FAST["left_grace"] / 4)
    call.senior_joins(mic=True)
    await asyncio.sleep(3 * FAST["left_grace"])
    assert call.deletes == 0 and not call.task.done(), "a rejoin inside the grace period must not hang up"
    call.room.leave(SENIOR)                # this time for good
    await until(lambda: call.deletes, "delete_room")
    assert await call.finish() == SENIOR_HUNG_UP
    assert call.deletes == 1 and not call.fallbacks and not call.sent


async def test_late_answer_after_the_ring_window_is_still_supervised():
    call = Call()
    call.senior_joins()
    await until(lambda: call.fallbacks, "no-answer stub")
    call.senior_answers()                  # CallKit can ring longer than our window
    await until(lambda: call.ring.answered, "answered")
    call.room.leave(SENIOR)
    await until(lambda: call.deletes, "delete_room")
    assert await call.finish() == SENIOR_HUNG_UP
    assert call.deletes == 1 and len(call.fallbacks) == 1


async def test_caller_leaving_stops_quietly():
    ringing = Call()
    await until(lambda: ringing.sent, "first invite")
    ringing.room.leave(CALLER)             # gave up while it was ringing
    assert await ringing.finish() == CALLER_LEFT
    n = len(ringing.sent)
    await asyncio.sleep(4 * FAST["resend_every"])
    assert len(ringing.sent) == n and not ringing.fallbacks and ringing.deletes == 0

    talking = Call()
    talking.senior_joins(mic=True)
    await until(lambda: talking.ring.answered, "answered")
    talking.room.leave(SENIOR)
    await asyncio.sleep(FAST["left_grace"] / 4)
    talking.room.leave(CALLER)             # both hung up: the room empties on its own
    assert await talking.finish() == CALLER_LEFT
    assert talking.deletes == 0 and not talking.fallbacks

    closed = Call()
    closed.room.connected = False          # room closed under the agent
    assert await closed.finish() == CALLER_LEFT
    assert closed.deletes == 0 and not closed.fallbacks


async def test_nothing_raises_when_the_api_throws():
    for failure in ("list", "send"):
        call = Call()
        call.lk.room.fail = failure
        await until(lambda: call.fallbacks, f"stub although {failure} fails")
        assert not call.sent and call.fallbacks[0]["reason"] == "timeout"
        call.room.leave(CALLER)
        assert await call.finish() == CALLER_LEFT

    hung = Call(api_timeout=0.05)          # a request that never returns must not stall the ring
    hung.lk.room.hang = True
    t0 = time.monotonic()
    await until(lambda: hung.fallbacks, "stub although the API hangs")
    assert time.monotonic() - t0 < 3 * FAST["ring_timeout"]
    await hung.close()

    def bad_mint(room_name):
        raise ValueError("api_key and api_secret must be set")
    no_token = Call(mint_token=bad_mint)
    await until(lambda: no_token.fallbacks, "stub although the token cannot be minted")
    assert not no_token.sent
    await no_token.close()

    def bad_stub(**kw):
        raise RuntimeError("fallback boom")
    bad = Call(no_answer=bad_stub)
    await asyncio.sleep(FAST["ring_timeout"] + 0.2)
    assert not bad.task.done()
    bad.room.leave(CALLER)
    assert await bad.finish() == CALLER_LEFT

    undeletable = Call()
    undeletable.delete_fails = True        # swallowed error, room stays connected: retried, then given up
    undeletable.senior_joins(mic=True)
    await until(lambda: undeletable.ring.answered, "answered")
    undeletable.room.leave(SENIOR)
    assert await undeletable.finish() == SENIOR_HUNG_UP
    assert undeletable.deletes == senior_ring.DELETE_ATTEMPTS, undeletable.deletes

    stuck = Call(api_timeout=0.05)
    stuck.delete_hangs = True              # a delete that never returns must not stall the ring either
    stuck.senior_joins(mic=True)
    await until(lambda: stuck.ring.answered, "answered")
    stuck.room.leave(SENIOR)
    assert await stuck.finish() == SENIOR_HUNG_UP
    assert stuck.deletes == senior_ring.DELETE_ATTEMPTS, stuck.deletes

    broken = Call()
    broken.room.remote_participants = None           # an unexpected bug inside the loop
    assert await broken.finish() == CRASHED


async def test_bad_ring_timeout_setting_never_breaks_the_agent():
    parse = senior_ring._ring_timeout_from_env       # no await below: nothing else sees the changed env
    saved = os.environ.get("RING_TIMEOUT_SEC")
    try:
        os.environ.pop("RING_TIMEOUT_SEC", None)
        assert parse() == 30.0
        for raw, want in [("", 30.0), ("45", 45.0), ("12.5", 12.5), ("5", 5.0), ("600", 600.0),
                          ("thirty", 30.0), ("30s", 30.0), (" ", 30.0), ("nan", 30.0), ("inf", 30.0),
                          ("-inf", 30.0), ("-5", 30.0), ("0", 30.0), ("4.9", 30.0), ("601", 30.0)]:
            os.environ["RING_TIMEOUT_SEC"] = raw
            assert parse() == want, (raw, parse())
    finally:
        if saved is None:
            os.environ.pop("RING_TIMEOUT_SEC", None)
        else:
            os.environ["RING_TIMEOUT_SEC"] = saved

    # The real failure was at import time, so check a fresh interpreter importing the module.
    here = os.path.dirname(os.path.abspath(__file__))

    def import_with(raw):
        r = subprocess.run([sys.executable, "-c", "import senior_ring as s; print(s.RING_TIMEOUT_SEC, s.CALL_TOKEN_TTL_SEC)"],
                           cwd=here, env=dict(os.environ, RING_TIMEOUT_SEC=raw),
                           capture_output=True, text=True, timeout=25)
        return r.returncode, r.stdout.strip(), r.stderr
    results = await asyncio.gather(*(asyncio.to_thread(import_with, raw) for raw in ("thirty", "nan", "400")))
    for (code, out, err), want in zip(results, ("30.0 600", "30.0 600", "400.0 760")):
        assert code == 0 and out == want, (code, out, err)
    assert "RING_TIMEOUT_SEC='thirty'" in results[0][2], "a bad value should be reported, not silently ignored"


async def test_state_changes_are_logged_once():
    records = []
    handler = logging.Handler()
    handler.emit = lambda r: records.append(r.getMessage())
    log = senior_ring.log
    old_level, old_propagate = log.level, log.propagate
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    log.propagate = False                  # collect here only, do not print
    try:
        call = Call(lobby=None, ring_timeout=5)
        await until(lambda: call.lk.room.list_calls >= 4, "lobby checks")
        call.lk.room.lobby = [SENIOR]
        await until(lambda: len(call.sent) >= 4, "invites")
        call.senior_joins()
        await asyncio.sleep(SETTLE)
        call.senior_answers()
        await until(lambda: call.ring.answered, "answered")
        await asyncio.sleep(SETTLE)
        await call.close()
    finally:
        log.removeHandler(handler)
        log.setLevel(old_level)
        log.propagate = old_propagate
    count = lambda text: sum(text in m for m in records)
    assert count("not connected to lobby") == 1, records
    assert count("invite sent") == 1, records
    assert count("senior joined") == 1 and count("senior answered") == 1, records
    assert count(repr(NUMBER)) == 1, "the caller number must be logged as the app receives it"
    assert not any("eyJ" in m for m in records), "the token must never be logged"


class FakeCtx:
    """The parts of JobContext that start_for_job uses."""

    def __init__(self, room, lk):
        self.room, self.api, self.deleted = room, lk, 0
        self._shutdown_callbacks = []

    # the installed framework's own registration code, so the callback's shape is checked for real
    add_shutdown_callback = JobContext.add_shutdown_callback

    async def delete_room(self):
        self.deleted += 1
        self.room.connected = False

    async def shutdown(self):
        for cb in self._shutdown_callbacks:
            await cb("room disconnected")


def ring_tasks():
    return [t for t in asyncio.all_tasks() if t.get_name() == "senior_ring" and not t.done()]


async def test_start_for_job_rings_once_for_a_real_sip_caller():
    opts = dict(FAST, ring_timeout=5, mint_token=mint)
    before = len(ring_tasks())

    room, lk = FakeRoom([Person("dev-watcher")]), FakeLK([SENIOR])
    ctx = FakeCtx(room, lk)
    senior_ring.start_for_job(ctx, **opts)
    room.join(Person("some-app-user"))                                       # not a phone caller
    room.join(Person("sip_outbound", SIP, {"sip.callStatus": "dialing"}))    # a call WE are placing
    await asyncio.sleep(4 * FAST["resend_every"])
    assert not lk.room.sent and len(ring_tasks()) == before

    room.join(Person(CALLER, SIP, {"sip.callStatus": "ringing", "sip.phoneNumber": NUMBER}))
    await until(lambda: lk.room.sent, "invite for the SIP caller")
    room.join(Person("sip_second", SIP, {"sip.callStatus": "ringing"}))
    await asyncio.sleep(4 * FAST["resend_every"])
    assert len(ring_tasks()) == before + 1, "exactly one ring per job"
    invites = [json.loads(r.data.decode("utf-8")) for r in lk.room.sent]
    assert len({i["callUUID"] for i in invites}) == 1
    assert invites[0]["handle"] == NUMBER and invites[0]["callerIdentity"] == CALLER
    assert invites[0]["room"] == room.name

    await ctx.shutdown()
    assert len(ring_tasks()) == before, "the ring task must be cancelled at job shutdown"

    # The caller is already in the room when the agent connects, and has no number.
    room2, lk2 = FakeRoom([Person(CALLER, SIP, {"sip.callStatus": "ringing"})]), FakeLK([SENIOR])
    ctx2 = FakeCtx(room2, lk2)
    senior_ring.start_for_job(ctx2, **opts)
    await until(lambda: lk2.room.sent, "invite for a caller who was already there")
    assert json.loads(lk2.room.sent[0].data)["handle"] == ""
    room2.join(Person(SENIOR, mic=True))                 # answers, then hangs up
    await asyncio.sleep(2 * SETTLE)
    room2.leave(SENIOR)
    await until(lambda: ctx2.deleted, "ctx.delete_room")
    await ctx2.shutdown()
    assert len(ring_tasks()) == before

    class NoApi(FakeCtx):
        @property
        def api(self):
            raise ValueError("url must be set")

        @api.setter
        def api(self, value):
            pass
    room3 = FakeRoom([Person(CALLER, SIP, {"sip.callStatus": "ringing"})])
    senior_ring.start_for_job(NoApi(room3, None), **opts)        # must not raise into the job
    assert len(ring_tasks()) == before


class AgentCtx(FakeCtx):
    """Adds what agent.scam_guard needs beyond start_for_job: connect, the detector, wait_for_participant."""

    def __init__(self, room, lk, wait):
        super().__init__(room, lk)
        self.proc = types.SimpleNamespace(userdata={"detector": types.SimpleNamespace(
            meta={"window_sec": 4.0}, device="fake")})
        self.wait = wait

    async def connect(self, **kw):
        pass

    async def wait_for_participant(self, **kw):
        return await self.wait()


async def test_scoring_trouble_never_takes_the_ring_down():
    # Any exception that escapes the entrypoint makes the framework disconnect the agent and run the
    # shutdown callbacks, which cancels the ring. So scam_guard must come back normally instead.
    import agent                           # not at the top of the file: heavier than the rest
    records = []
    handler = logging.Handler()
    handler.emit = lambda r: records.append((r.levelno, r.getMessage()))
    log = agent.log
    old_level, old_propagate = log.level, log.propagate
    old_thresholds = agent.detector_adapter.thresholds
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    log.propagate = False                  # collect here only, do not print
    ctxs = []

    def new_ctx(wait):
        room = FakeRoom([Person(CALLER, SIP, {"sip.callStatus": "ringing", "sip.phoneNumber": NUMBER})])
        ctxs.append(AgentCtx(room, FakeLK([SENIOR]), wait))
        return ctxs[-1]

    def scoring_errors():
        return [m for lvl, m in records if lvl >= logging.ERROR and "scoring stopped" in m]

    async def never():
        await asyncio.Event().wait()

    try:
        before = len(ring_tasks())

        def typo_in_a_secret(det):         # what float("19,0") in detector_adapter.thresholds does
            raise ValueError("could not convert string to float: '19,0'")
        agent.detector_adapter.thresholds = typo_in_a_secret
        ctx = new_ctx(never)
        await agent.scam_guard(ctx)        # must not raise
        assert len(scoring_errors()) == 1, records
        assert len(ring_tasks()) == before + 1, "the ring must still be running"
        await asyncio.sleep(2 * SETTLE)
        assert len(ring_tasks()) == before + 1 and not ctx.deleted
        await ctx.shutdown()               # what the framework does when the room disconnects
        assert len(ring_tasks()) == before

        agent.detector_adapter.thresholds = lambda det: (0.9, 0.99)
        records.clear()
        broken = new_ctx(None)
        async def real_bug():
            raise RuntimeError("boom")     # a RuntimeError while the room is still up is a real error
        broken.wait = real_bug
        await agent.scam_guard(broken)
        assert len(scoring_errors()) == 1 and len(ring_tasks()) == before + 1, records
        await broken.shutdown()

        records.clear()
        closed = new_ctx(None)
        async def caller_gave_up():        # what wait_for_participant does when the room closes first
            closed.room.connected = False
            raise RuntimeError("room disconnected while waiting for participant")
        closed.wait = caller_gave_up
        await agent.scam_guard(closed)
        assert not scoring_errors(), records
        assert any("room closed before scoring finished" in m for _, m in records), records

        cancelled = new_ctx(never)         # cancellation (job shutdown) must still get through
        task = asyncio.create_task(agent.scam_guard(cancelled))
        await asyncio.sleep(2 * SETTLE)
        assert not task.done()
        task.cancel()
        result, = await asyncio.gather(task, return_exceptions=True)
        assert isinstance(result, asyncio.CancelledError), result
    finally:
        agent.detector_adapter.thresholds = old_thresholds
        log.removeHandler(handler)
        log.setLevel(old_level)
        log.propagate = old_propagate
        for c in ctxs:
            await c.shutdown()
    assert len(ring_tasks()) == before


# ---------------------------------------------------------------- runner

async def main() -> int:
    tests = [(name, fn) for name, fn in globals().items() if name.startswith("test_")]
    t0 = time.monotonic()

    async def run_one(name, fn):
        t = time.monotonic()
        try:
            await asyncio.wait_for(fn(), timeout=30)
            return name, None, time.monotonic() - t
        except BaseException as e:           # report every failure, keep the other tests running
            import traceback
            return name, "".join(traceback.format_exception(e)), time.monotonic() - t

    # The log test attaches a handler to the shared logger, and the scoring test counts ring tasks
    # (as does the start_for_job test), so those two run on their own afterwards.
    alone = ("test_state_changes_are_logged_once", "test_scoring_trouble_never_takes_the_ring_down")
    results = list(await asyncio.gather(*(run_one(n, f) for n, f in tests if n not in alone)))
    results += [await run_one(n, f) for n, f in tests if n in alone]

    failed = 0
    for name, err, secs in results:
        print(f"{'FAIL' if err else 'PASS'}  {name}  ({secs:.2f}s)")
        if err:
            failed += 1
            print(err)
    print(f"\n{len(results) - failed} passed, {failed} failed in {time.monotonic() - t0:.1f}s")
    return 1 if failed else 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.CRITICAL)      # the ring's own log lines would bury the results
    sys.exit(asyncio.run(main()))
