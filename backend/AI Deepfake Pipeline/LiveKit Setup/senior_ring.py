"""Ring the senior's iPhone when a phone call arrives (foreground-only ring: no PushKit, no APNs).

How the phone is reached
  While the Callshield app is open it stays connected to a small LiveKit "lobby" room. When a
  real phone caller is waiting in a call room, scam-guard sends the app an invite through the
  LiveKit server API: a data message on topic "callshield.incoming" that names the call room and
  carries a short-lived token for it plus the caller's number. The app shows the native CallKit
  screen and joins the call room silently. Only when the senior answers does it publish its
  microphone. LiveKit keeps the phone caller ringing until some participant publishes audio, so
  that microphone publish IS the answer. Only after pickup does scam-guard publish its
  brief recording announcement; the ring supervisor does not depend on that playback.

What SeniorRing decides, once per call
  - re-sends the same invite every ~3 s until the senior has joined the call room, the caller
    has left, or the ring window (~30 s) is over;
  - "answered" = the senior identity has a microphone track in the call room;
  - no answer (ring window over, or the senior left without answering: decline / CallKit ring
    timeout) -> no_answer_fallback() exactly once, then delete the room to disconnect the caller;
  - senior left after answering and did not come back within a few seconds -> delete the room,
    which disconnects the phone caller;
  - caller left -> stop quietly.

It polls the room instead of reacting to events, so it also copes with people who were already
there when it started. It never raises into the job and shares nothing with the scoring loop.
The API object, the room and the timings are parameters: test_senior_ring.py drives it with fakes.

To ring through a VoIP push later, replace notify_senior() only.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import time
import uuid
from datetime import timedelta
from typing import Any, Awaitable, Callable

from dotenv import load_dotenv
from livekit import api, rtc
from safety_store import configured_block_check

HERE = os.path.dirname(os.path.abspath(__file__))
# agent.py imports this module before its own load_dotenv, and the settings below are read at
# import, so load .env.local here too. On LiveKit Cloud there is no .env file and this does nothing.
load_dotenv(os.path.join(HERE, ".env.local"))

log = logging.getLogger("scam-guard.ring")


def _ring_timeout_from_env(default: float = 30.0, lowest: float = 5.0, highest: float = 600.0) -> float:
    """RING_TIMEOUT_SEC, or `default` when it is unset or unusable. This runs at import, so it must
    never raise: a typo in a Cloud secret ("30s") must not stop the whole agent from starting.
    Unusable = not a number, nan/inf, below `lowest` (the first invite would not even go out
    before the call times out) or above `highest`."""
    raw = os.environ.get("RING_TIMEOUT_SEC")
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        value = math.nan
    if not lowest <= value <= highest:         # also false for nan
        log.warning("RING_TIMEOUT_SEC=%r is not a number of seconds between %g and %g; using %g",
                    raw, lowest, highest, default)
        return default
    return value


SENIOR_IDENTITY = os.environ.get("SENIOR_IDENTITY") or "senior"        # same in lobby and call room
SENIOR_LOBBY_ROOM = os.environ.get("SENIOR_LOBBY_ROOM") or "senior-lobby"
INCOMING_TOPIC = "callshield.incoming"       # fixed by the wire contract with the iOS app
RING_TIMEOUT_SEC = _ring_timeout_from_env()
RESEND_EVERY_SEC = 3.0         # the app ignores repeats of a callUUID it has already handled
SENIOR_LEFT_GRACE_SEC = 5.0    # a network blip also looks like "left": wait before acting on it
POLL_EVERY_SEC = 0.25          # how often the call room is looked at
API_TIMEOUT_SEC = 5.0          # per server API call, so a hung request cannot stall the ring
# The token is minted once per call, and the app joins with it at the latest about RING_TIMEOUT_SEC
# later (late re-sends carry it). The open-source livekit-server sends a joined client a refreshed
# token right after its session starts (pkg/service/roommanager.go, rtcSessionWorker) and again
# every 5 minutes, and the Swift SDK (2.17.0) stores it and presents it on a reconnect
# (Room+Engine.swift reads _state.token). LiveKit Cloud's refresh behaviour is not public, though,
# and an expired token would drop an answered call at a Wi-Fi/cellular handover. So the lifetime
# is kept as a margin over the ring window: 10 minutes, or RING_TIMEOUT_SEC + 6 minutes if that is
# longer. The cost of the longer life is small: re-sends stop within the ring window, and the
# grants are one room, join + microphone only.
CALL_TOKEN_TTL_SEC = max(600, math.ceil(RING_TIMEOUT_SEC) + 360)
DELETE_ATTEMPTS = 3

# What SeniorRing.run() returns.
CALLER_LEFT = "caller_left"
SENIOR_HUNG_UP = "senior_hung_up"
UNANSWERED = "unanswered"
CLEANUP_FAILED = "cleanup_failed"
CRASHED = "error"
BLOCKED = "blocked"


def senior_has_microphone(room: Any, *, identity: str = SENIOR_IDENTITY) -> bool:
    """Only the app's microphone publication proves pickup, even when SIP is active."""
    senior = room.remote_participants.get(identity)
    return senior is not None and any(
        pub.source == rtc.TrackSource.SOURCE_MICROPHONE
        for pub in senior.track_publications.values())


async def wait_for_answer(room: Any, caller_identity: str, *,
                          senior_identity: str = SENIOR_IDENTITY,
                          poll_every: float = POLL_EVERY_SEC) -> bool:
    """Wait for Callma Accept, or return False when the caller/room goes away.

    SIP can become active before the app answers. Publishing the notice at that point
    would answer the telephone itself. A silent app join, the caller's microphone and
    other app tracks therefore never release this gate. The playback timeout starts
    only after this wait; an unanswered ring can last longer than that timeout.
    """
    while room.isconnected() and caller_identity in room.remote_participants:
        if senior_has_microphone(room, identity=senior_identity):
            return True
        await asyncio.sleep(poll_every)
    return False


def mint_call_token(room_name: str, *, identity: str = SENIOR_IDENTITY,
                    ttl_sec: float = CALL_TOKEN_TTL_SEC,
                    api_key: str | None = None, api_secret: str | None = None) -> str:
    """Token that lets the senior join ONE call room: listen, and publish a microphone only.

    Key and secret default to LIVEKIT_API_KEY / LIVEKIT_API_SECRET (injected on LiveKit Cloud).
    """
    return (api.AccessToken(api_key, api_secret)
            .with_identity(identity)
            .with_ttl(timedelta(seconds=ttl_sec))
            .with_grants(api.VideoGrants(room_join=True, room=room_name,
                                         can_subscribe=True,
                                         can_publish=True, can_publish_sources=["microphone"],
                                         can_publish_data=False))
            .to_jwt())


def mint_lobby_token(*, ttl_days: float = 30, identity: str = SENIOR_IDENTITY,
                     lobby_room: str = SENIOR_LOBBY_ROOM,
                     api_key: str | None = None, api_secret: str | None = None) -> str:
    """Long-lived token the app uses to sit in the lobby and receive invites. It cannot publish."""
    return (api.AccessToken(api_key, api_secret)
            .with_identity(identity)
            .with_ttl(timedelta(days=ttl_days))
            .with_grants(api.VideoGrants(room_join=True, room=lobby_room,
                                         can_publish=False, can_publish_data=False))
            .to_jwt())


def build_invite(*, call_uuid: str, room_name: str, token: str, handle: str,
                 caller_identity: str, caller_name: str | None = None) -> dict:
    """The "incoming call" message. WIRE CONTRACT with the iOS app: do not rename or add keys.

    callUUID        one per call; the app uses it as the CallKit UUID and to ignore repeats
    room / token    the call room and a short-lived token to join it as the senior
    handle          caller's number as LiveKit saw it (sip.phoneNumber); "" if there is none
    callerIdentity  the caller's participant identity; the app treats THAT participant leaving
                    as "caller hung up"
    callerName      optional
    """
    invite = {"type": "incoming_call", "callUUID": call_uuid, "room": room_name, "token": token,
              "handle": handle or "", "callerIdentity": caller_identity}
    if caller_name:
        invite["callerName"] = caller_name
    return invite


async def notify_senior(lk: Any, invite: dict, *, lobby_room: str = SENIOR_LOBBY_ROOM,
                        senior_identity: str = SENIOR_IDENTITY) -> bool:
    """Deliver the invite to the senior's phone. False = the app is not reachable right now.

    This is the ONLY function that knows how the phone is reached. Today: a reliable data message
    to the lobby room the open app sits in. A VoIP push (APNs) sender would replace this function.

    lk: api.LiveKitAPI (ctx.api in the agent). Errors other than "no such room" are raised.
    """
    try:
        resp = await lk.room.list_participants(api.ListParticipantsRequest(room=lobby_room))
    except api.TwirpError as e:
        if e.code == api.TwirpErrorCode.NOT_FOUND:      # no lobby room = the app is not connected
            return False
        raise
    if not any(p.identity == senior_identity for p in resp.participants):
        return False
    # RoomService.send_data fills in the nonce itself.
    await lk.room.send_data(api.SendDataRequest(
        room=lobby_room,
        data=json.dumps(invite).encode("utf-8"),
        kind=api.DataPacket.Kind.RELIABLE,
        destination_identities=[senior_identity],
        topic=INCOMING_TOPIC,
    ))
    return True


def no_answer_fallback(*, room_name: str, call_uuid: str, handle: str, reason: str) -> None:
    """Optional notification hook. Called exactly once when the senior did not pick up.

    reason: "timeout" (ring window over) or "declined" (the senior's app left the call room
    without answering: decline, or the phone's own ring timeout).

    Known limitation: "declined" is only seen once the senior's app has been in the call room.
    A decline that happens earlier (declining while the app is still joining, Do Not Disturb
    refusing the CallKit call, a failed join) leaves no trace here and arrives as "timeout" at the
    end of the ring window. Do not branch on the reason or the timing alone. Returning to the
    lobby cannot stand in as the signal: the app also drops and rejoins the lobby when it is
    backgrounded or loses its network, before it has seen any invite.

    TODO(team): this is where "agent takes a message + notify family" will go. Not built yet.
    SeniorRing deletes the call room after this hook, disconnecting the caller even if the hook
    raises. This runs inside the ring loop, so keep it quick or start a task.
    """
    log.info("NO-ANSWER (%s): room=%s callUUID=%s caller number=%r; disconnecting caller.",
             reason, room_name, call_uuid, handle)


class SeniorRing:
    """Ring the senior for one incoming call and supervise it. See the module docstring.

    lk           api.LiveKitAPI, or anything with .room.list_participants / .room.send_data
    room         rtc.Room the caller is in (needs .name, .isconnected(), .remote_participants)
    delete_room  called with no arguments, returns an awaitable; JobContext.delete_room fits
    caller_is_local  True when this process IS the caller (tools/test_ring.py)
    """

    def __init__(self, *, lk: Any, room: Any, caller_identity: str, handle: str,
                 delete_room: Callable[[], Awaitable[Any]],
                 caller_name: str | None = None, caller_is_local: bool = False,
                 senior_identity: str = SENIOR_IDENTITY, lobby_room: str = SENIOR_LOBBY_ROOM,
                 ring_timeout: float = RING_TIMEOUT_SEC, resend_every: float = RESEND_EVERY_SEC,
                 left_grace: float = SENIOR_LEFT_GRACE_SEC, poll_every: float = POLL_EVERY_SEC,
                 api_timeout: float = API_TIMEOUT_SEC,
                 mint_token: Callable[[str], str] = mint_call_token,
                 notify: Callable[..., Awaitable[bool]] = notify_senior,
                 no_answer: Callable[..., None] = no_answer_fallback,
                 block_check: Callable[[str, str], bool] = configured_block_check) -> None:
        self._lk, self._room, self._delete_room = lk, room, delete_room
        self._caller_identity, self._caller_is_local = caller_identity, caller_is_local
        self._handle, self._caller_name = handle or "", caller_name
        self._senior_identity, self._lobby_room = senior_identity, lobby_room
        self._ring_timeout, self._resend_every = ring_timeout, resend_every
        self._left_grace, self._poll_every, self._api_timeout = left_grace, poll_every, api_timeout
        self._mint_token, self._notify, self._no_answer = mint_token, notify, no_answer
        self._block_check = block_check
        self.call_uuid = str(uuid.uuid4())     # one per call: every re-send carries the same one
        self.joined = False                    # senior has been seen in the call room
        self.answered = False                  # senior has published a microphone track

    async def run(self) -> str:
        """Returns CALLER_LEFT, SENIOR_HUNG_UP, UNANSWERED, BLOCKED, CLEANUP_FAILED, or CRASHED.
        Never raises, except when cancelled. CLEANUP_FAILED means the caller may still be connected.
        """
        try:
            return await self._run()
        except Exception:        # not BaseException: cancellation at job shutdown must get through
            log.exception("senior ring crashed; this call is no longer supervised by it")
            return CRASHED

    def _caller_here(self) -> bool:
        if not self._room.isconnected():       # room deleted or closed: everyone is gone
            return False
        return self._caller_is_local or self._caller_identity in self._room.remote_participants

    async def _run(self) -> str:
        room, name = self._room, self._room.name
        # Only explicit manual personal blocks or separately reviewed shared blocks
        # are consulted. Model scores never enter this decision. Do this before
        # minting a call token or sending an incoming-call invite.
        try:
            blocked = await asyncio.wait_for(
                asyncio.to_thread(self._block_check, self._senior_identity, self._handle),
                self._api_timeout)
        except Exception:
            blocked = False
            log.warning("manual block lookup unavailable; allowing this call to ring")
        if blocked:
            for attempt in range(DELETE_ATTEMPTS):
                if not self._caller_here():
                    return BLOCKED
                try:
                    await asyncio.wait_for(self._delete_room(), self._api_timeout)
                except Exception:
                    log.warning("manual block disconnect failed; retrying")
                if not self._caller_here():
                    return BLOCKED
                if attempt + 1 < DELETE_ATTEMPTS:
                    await asyncio.sleep(self._resend_every)
            log.error("could not disconnect a manually blocked call")
            return CLEANUP_FAILED
        invite = None
        try:
            invite = build_invite(call_uuid=self.call_uuid, room_name=name,
                                  token=self._mint_token(name), handle=self._handle,
                                  caller_identity=self._caller_identity,
                                  caller_name=self._caller_name)
        except Exception as e:   # e.g. LIVEKIT_API_SECRET missing. Keep supervising the call anyway.
            log.error("cannot ring the senior for %s: minting the call token failed: %s", name, e)
        # The team still needs to learn whether the original caller ID survives carrier
        # forwarding. This is the number exactly as the app receives it.
        log.info("incoming call in %s: callUUID=%s caller=%s number sent to the app (sip.phoneNumber)=%r",
                 name, self.call_uuid, self._caller_identity, self._handle)

        start = time.monotonic()
        ring_until = start + self._ring_timeout
        next_send = start
        delivery = None           # last logged delivery state, so each change is logged once
        no_answer_done = False    # the fallback fires at most once per call
        left_at = None            # when the senior was first seen missing after having joined
        deletes, next_delete = 0, start

        while True:
            now = time.monotonic()
            if not self._caller_here():
                if deletes:
                    return UNANSWERED if no_answer_done else SENIOR_HUNG_UP
                log.info("%s; nothing more to do",
                         f"caller left {name}" if room.isconnected() else f"room {name} closed")
                return CALLER_LEFT

            # Match the senior on identity, not on participant kind.
            senior = room.remote_participants.get(self._senior_identity)
            if no_answer_done:
                pass    # terminal: a late join or microphone must not cancel room cleanup
            elif senior is not None:
                if not self.joined:
                    self.joined = True
                    log.info("senior joined %s (phone is ringing, not answered yet)", name)
                elif left_at is not None:
                    log.info("senior is back in %s", name)
                left_at = None
                # Only the senior's own microphone counts. The caller publishes while ringing too.
                if not self.answered and senior_has_microphone(room, identity=self._senior_identity):
                    self.answered = True
                    log.info("senior answered %s after %.1fs (microphone published)", name, now - start)
            elif self.joined and left_at is None:
                left_at = now
                log.info("senior left %s %s; waiting %gs in case they come back", name,
                         "after answering" if self.answered else "without answering", self._left_grace)
            gone = left_at is not None and now - left_at >= self._left_grace

            if not self.answered and not no_answer_done:
                reason = "declined" if gone else "timeout" if now >= ring_until else None
                if reason is not None:
                    no_answer_done = True     # terminal decision: stop invites and disconnect the caller
                    log.info("no answer in %s: %s", name,
                             "the senior declined or the phone stopped ringing" if reason == "declined"
                             else f"not answered within {self._ring_timeout:g}s")
                    try:
                        self._no_answer(room_name=name, call_uuid=self.call_uuid,
                                        handle=self._handle, reason=reason)
                    except Exception:
                        log.exception("no-answer fallback failed")
                elif invite is not None and not self.joined and now >= next_send:
                    next_send = now + self._resend_every
                    state, detail = await self._deliver(invite)
                    if state != delivery:
                        previous, delivery = delivery, state
                        if state == "sent":
                            log.info("invite sent to %r in lobby %s; re-sending every %gs until "
                                     "they join the call room", self._senior_identity,
                                     self._lobby_room, self._resend_every)
                        elif state == "offline" and previous == "sent":
                            # Normal right after an invite: the app drops the lobby, then joins here.
                            log.info("senior app is no longer in lobby %s (it leaves the lobby to "
                                     "join the call room, or it was closed)", self._lobby_room)
                        elif state == "offline":
                            log.info("senior app not connected to lobby %s (is the app open?); "
                                     "checking again every %gs", self._lobby_room, self._resend_every)
                        else:
                            log.warning("could not send the invite (%s); retrying every %gs",
                                        detail, self._resend_every)

            if no_answer_done or (self.answered and gone):
                if now >= next_delete:
                    if deletes >= DELETE_ATTEMPTS:
                        log.error("could not delete %s after %d attempts; the phone caller is "
                                  "still connected", name, deletes)
                        return CLEANUP_FAILED
                    deletes += 1
                    next_delete = now + self._resend_every
                    log.info("%s; deleting %s so the phone caller is disconnected "
                             "(attempt %d)", "no answer" if no_answer_done else "senior hung up",
                             name, deletes)
                    # JobContext.delete_room logs its own API errors and never raises, so a failed
                    # delete shows up as the room still being connected: the loop then comes back
                    # here after resend_every, up to DELETE_ATTEMPTS. This except only catches the
                    # api_timeout (and whatever another delete_room might raise).
                    try:
                        await asyncio.wait_for(self._delete_room(), self._api_timeout)
                    except Exception as e:
                        log.warning("deleting %s failed: %r", name, e)

            await asyncio.sleep(self._poll_every)

    async def _deliver(self, invite: dict) -> tuple[str, str]:
        """("sent" | "offline" | "failed", detail). Never raises."""
        try:
            sent = await asyncio.wait_for(
                self._notify(self._lk, invite, lobby_room=self._lobby_room,
                             senior_identity=self._senior_identity),
                self._api_timeout)
        except Exception as e:
            return "failed", repr(e)
        return ("sent" if sent else "offline"), ""


def is_incoming_caller(participant: Any) -> bool:
    """A real incoming phone call: a SIP participant that is not an outbound call being dialed."""
    return (participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
            and participant.attributes.get("sip.callStatus") != "dialing")


def start_for_job(ctx: Any, **ring_options: Any) -> None:
    """Called by agent.py right after ctx.connect(). Starts ONE SeniorRing for the job's phone
    caller, whether they are already in the room or connect later, and returns immediately.

    The ring must not wait for JobContext.wait_for_participant: that only returns once the SIP
    participant is ACTIVE, and nothing answers the call until the senior has been rung.
    The ring task outlives the audio loop (it still has to notice the senior hanging up while
    the caller is connected), so it is cancelled at job shutdown, not in the entrypoint.
    """
    room = ctx.room
    task: asyncio.Task | None = None

    def maybe_start(participant: Any) -> None:
        nonlocal task
        try:
            if task is not None or not is_incoming_caller(participant):
                return
            ring = SeniorRing(lk=ctx.api, room=room, caller_identity=participant.identity,
                              handle=participant.attributes.get("sip.phoneNumber", ""),
                              delete_room=ctx.delete_room, **ring_options)
            task = asyncio.create_task(ring.run(), name="senior_ring")
        except Exception:
            log.exception("could not start the senior ring")

    async def stop_ring() -> None:
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    try:
        # No await between the scan and the listener, so a caller cannot slip in between.
        for p in list(room.remote_participants.values()):
            maybe_start(p)
        room.on("participant_connected", maybe_start)
        ctx.add_shutdown_callback(stop_ring)
    except Exception:            # ringing must never take the scoring job down with it
        log.exception("could not set up the senior ring")
