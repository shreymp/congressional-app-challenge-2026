"""Print the two values the iOS app needs to sit in the senior "lobby" room and be rung.

The app stays connected to the lobby while it is open; scam-guard sends the "incoming call"
invite there (see senior_ring.py). The token only lets the app join that one room and listen:
it cannot publish audio or data.

Usage (from the LiveKit Setup folder, venv active):
  python tools/mint_lobby_token.py             # token valid for 30 days
  python tools/mint_lobby_token.py --days 7

Paste the two printed lines into ios/Configuration/Local.xcconfig (gitignored). The token is a
credential: do not commit it. Mint a new one before it expires, or if SENIOR_IDENTITY /
SENIOR_LOBBY_ROOM change.
"""
import argparse
import os
import sys
from datetime import datetime, timedelta
from urllib.parse import urlparse

from dotenv import load_dotenv

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(HERE, ".env.local"))
sys.path.insert(0, HERE)

import senior_ring  # noqa: E402  (needs the folder above on sys.path)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--days", type=float, default=30, help="how long the token stays valid (default 30)")
    a = ap.parse_args()

    missing = [k for k in ("LIVEKIT_API_KEY", "LIVEKIT_API_SECRET") if not os.environ.get(k)]
    if missing:
        sys.exit(f"Not set: {', '.join(missing)}. Fill in {os.path.join(HERE, '.env.local')} "
                 "(copy .env.example; the values are in LiveKit Cloud -> Settings -> API keys).")

    token = senior_ring.mint_lobby_token(ttl_days=a.days)
    url = os.environ.get("LIVEKIT_URL", "")
    host = urlparse(url if "://" in url else "wss://" + url).hostname or ""

    print(f"// Lobby room \"{senior_ring.SENIOR_LOBBY_ROOM}\", identity \"{senior_ring.SENIOR_IDENTITY}\", "
          f"expires {datetime.now() + timedelta(days=a.days):%Y-%m-%d}.")
    if host:
        print(f"CALLMA_LIVEKIT_HOST = {host}")
    else:
        # Commented out on purpose: a live placeholder line would be valid xcconfig and give the
        # app a broken host, while an unset host is treated by the app as "not configured".
        print("// LIVEKIT_URL is not set in .env.local. Add the next line with your project's host, "
              "without wss://")
        print("// CALLMA_LIVEKIT_HOST = <your-project-subdomain>.livekit.cloud")
    print(f"CALLMA_LOBBY_TOKEN = {token}")


if __name__ == "__main__":
    main()
