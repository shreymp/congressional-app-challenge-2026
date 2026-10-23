"""Manual block/report API. Bind locally behind an HTTPS proxy for real devices.

Run: python safety_service.py --db /private/path/callma.sqlite3
CALLMA_SAFETY_TOKENS_JSON is a JSON object mapping opaque tokens to user IDs.
The user ID must match the recipient's SENIOR_IDENTITY in the ring worker.
An independent CALLMA_SAFETY_ADMIN_TOKEN permits reviewed shared-block writes.
No guardian messages, call audio, or transcript data are sent by this service.
"""
from __future__ import annotations

import argparse
import hmac
import json
import os
import re
import threading
import time
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

from safety_store import SafetyStore


def load_tokens():
    tokens = json.loads(os.environ.get("CALLMA_SAFETY_TOKENS_JSON", "{}"))
    if not isinstance(tokens, dict) or not tokens:
        raise ValueError("Configure CALLMA_SAFETY_TOKENS_JSON before starting the service")
    if any(not isinstance(k, str) or len(k) < 32 or not isinstance(v, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", v) for k,v in tokens.items()):
        raise ValueError("Tokens must have >=32 characters and user IDs must be 1-64 simple characters")
    return tokens


def make_server(store, tokens, admin_token=None, host="127.0.0.1", port=8010):
    if not tokens or any(not isinstance(t, str) or len(t) < 32 or not t.isascii() for t in tokens):
        raise ValueError("Opaque per-user tokens of at least 32 characters are required")
    if admin_token and (len(admin_token) < 32 or not admin_token.isascii() or admin_token in tokens):
        raise ValueError("Admin token must be independent and at least 32 characters")
    attempts = defaultdict(deque)
    rate_lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def log_message(self, *_):
            pass  # never log bearer tokens, number paths, or report bodies

        def reply(self, status, body):
            data = json.dumps(body, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(data)

        def route(self):
            path = urlsplit(self.path).path
            if self.command == "GET" and path == "/health":
                return self.reply(200, {"ok": True})
            auth = self.headers.get("Authorization", "")
            supplied = auth[7:] if auth.startswith("Bearer ") else ""
            if not supplied.isascii():
                return self.reply(401, {"error": "Authentication required"})
            user = next((u for token,u in tokens.items() if hmac.compare_digest(token, supplied)), None)
            admin = bool(admin_token and hmac.compare_digest(admin_token, supplied))
            admin_path = path.startswith("/v1/admin/")
            if (admin_path and not admin) or (not admin_path and user is None):
                return self.reply(401, {"error": "Authentication required"})
            if self.command != "GET":
                with rate_lock:
                    queue = attempts[("admin", None) if admin_path else ("user", user)]
                    now = time.monotonic()
                    while queue and queue[0] < now - 60:
                        queue.popleft()
                    if len(queue) >= 30:
                        return self.reply(429, {"error": "Too many changes; try again shortly"})
                    queue.append(now)
            body = {}
            if self.command == "POST":
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if self.headers.get("Transfer-Encoding") or not 0 < length <= 4096:
                        return self.reply(413, {"error": "Invalid body size"})
                    body = json.loads(self.rfile.read(length))
                    if not isinstance(body, dict):
                        raise ValueError()
                except (ValueError, TimeoutError):
                    return self.reply(400, {"error": "Expected a JSON object"})
            try:
                if self.command == "GET" and path == "/v1/blocks":
                    return self.reply(200, store.list_for_user(user))
                if self.command == "POST" and path == "/v1/blocks":
                    return self.reply(201, store.block(user, body.get("number"), body.get("reason", ""), body.get("report", False), body.get("category", "scam")))
                if self.command == "DELETE" and path.startswith("/v1/blocks/"):
                    return self.reply(200, store.unblock(user, unquote(path[len("/v1/blocks/"):])))
                if self.command == "POST" and path == "/v1/reports":
                    return self.reply(201, store.report(user, body.get("number"), body.get("category", "scam"), body.get("notes", "")))
                if self.command == "POST" and path == "/v1/admin/shared-blocks":
                    return self.reply(201, store.review_shared(body.get("number"), body.get("reason", ""), body.get("reportId")))
                if self.command == "DELETE" and path.startswith("/v1/admin/shared-blocks/"):
                    return self.reply(200, store.remove_shared(unquote(path[len("/v1/admin/shared-blocks/"):])))
            except ValueError as error:
                return self.reply(400, {"error": str(error)})
            except Exception:
                return self.reply(503, {"error": "Safety service temporarily unavailable"})
            self.reply(404, {"error": "Not found"})

        do_GET = route
        do_POST = route
        do_DELETE = route

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    return server


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=os.environ.get("CALLMA_SAFETY_DB"), required=not bool(os.environ.get("CALLMA_SAFETY_DB")))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8010)
    args = parser.parse_args()
    server = make_server(SafetyStore(args.db), load_tokens(), os.environ.get("CALLMA_SAFETY_ADMIN_TOKEN"), args.host, args.port)
    print(f"callma. safety service listening on {args.host}:{args.port}; no external messages are sent", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
