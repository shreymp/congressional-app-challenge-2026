"""Stand-in for grandma's app: joins a call room invisibly and prints scam-guard's updates.

Usage (from the LiveKit Setup folder, venv active):
  python tools/watch_risk.py                 # joins the newest call-* room
  python tools/watch_risk.py call-+1312...   # joins a specific room

Start it after the test call has connected (the room only exists during a call).
"""
import asyncio
import json
import os
import sys

from dotenv import load_dotenv
from livekit import api, rtc

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(HERE, ".env.local"))


async def main() -> None:
    url = os.environ["LIVEKIT_URL"]
    async with api.LiveKitAPI() as lk:
        if len(sys.argv) > 1:
            room_name = sys.argv[1]
        else:
            rooms = (await lk.room.list_rooms(api.ListRoomsRequest())).rooms
            calls = sorted((r for r in rooms if r.name.startswith("call-")),
                           key=lambda r: r.creation_time, reverse=True)
            if not calls:
                sys.exit("No active call-* room. Place the test call first, then run this.")
            room_name = calls[0].name

    token = (api.AccessToken()
             .with_identity("dev-watcher")
             .with_grants(api.VideoGrants(room_join=True, room=room_name, hidden=True,
                                          can_publish=False, can_subscribe=False))
             .to_jwt())

    room = rtc.Room()
    done = asyncio.Event()

    @room.on("data_received")
    def _on_data(pkt: rtc.DataPacket):
        if pkt.topic != "scam-guard.risk":
            return
        m = json.loads(pkt.data)
        if m.get("type") == "risk":
            d = m["deepfake"]
            transcript = m.get("transcript") or {}
            probability = transcript.get("probability")
            text_score = "-" if probability is None else f"{probability:.3f}"
            print(f"model={m.get('model', 'unversioned')} seq={m.get('sequence', '-')} "
                  f"t={m['t']:6.1f}s  level={m['level']:10} logit={d['logit_last']:6.2f} "
                  f"smoothed_logit={d['logit_smoothed']:6.2f}  infer={m['infer_ms']}ms  voiced={m['voiced_sec']}s "
                  f"transcript={transcript.get('state', 'disabled')} p={text_score} "
                  f"revision={transcript.get('scored_revision', '-')}/{transcript.get('revision', '-')}")
        else:
            print(m)

    @room.on("disconnected")
    def _on_disc(*_):
        done.set()

    await room.connect(url, token)
    print(f"watching {room_name} (Ctrl+C to stop)")
    await done.wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass


