"""Persistent manual blocks and reports. No risk score can write a block.

Personal blocks take effect immediately. Reports require a separate human/admin
decision before a shared block can affect other users. Caller ID can be spoofed.
No audio or transcript is accepted by this store.
"""
from __future__ import annotations

import os
import re
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


def normalize_number(value: str) -> str:
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError("Use an international phone number beginning with +")
    number = re.sub(r"[\s().-]", "", value)
    if not re.fullmatch(r"\+[1-9][0-9]{7,14}", number):
        raise ValueError("Use an international phone number beginning with +")
    return number


def _text(value, limit):
    if not isinstance(value, str) or len(value) > limit or any(ord(c) < 32 for c in value):
        raise ValueError("Invalid text field")
    return value.strip()


class SafetyStore:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS personal_blocks (
                    user_id TEXT NOT NULL, number TEXT NOT NULL, reason TEXT NOT NULL,
                    created_at REAL NOT NULL, PRIMARY KEY(user_id, number));
                CREATE TABLE IF NOT EXISTS reports (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, number TEXT NOT NULL,
                    category TEXT NOT NULL, notes TEXT NOT NULL, status TEXT NOT NULL,
                    created_at REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS reports_user ON reports(user_id, created_at);
                CREATE TABLE IF NOT EXISTS shared_blocks (
                    number TEXT PRIMARY KEY, reason TEXT NOT NULL,
                    report_id TEXT, created_at REAL NOT NULL);
            """)
        os.chmod(self.path, 0o600)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=2)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def block_item(row, scope):
        return {"number": row["number"], "scope": scope,
                "createdAt": row["created_at"], "reason": row["reason"]}

    @staticmethod
    def report_item(row):
        return {"id": row["id"], "number": row["number"], "category": row["category"],
                "status": row["status"], "createdAt": row["created_at"]}

    def list_for_user(self, user_id):
        with self.connection() as db:
            personal = db.execute("SELECT * FROM personal_blocks WHERE user_id=? ORDER BY created_at DESC", (user_id,)).fetchall()
            shared = db.execute("SELECT * FROM shared_blocks ORDER BY created_at DESC").fetchall()
            reports = db.execute("SELECT * FROM reports WHERE user_id=? ORDER BY created_at DESC LIMIT 200", (user_id,)).fetchall()
        return {"blocks": [self.block_item(r, "personal") for r in personal] + [self.block_item(r, "shared") for r in shared],
                "reports": [self.report_item(r) for r in reports]}

    def block(self, user_id, number, reason="", report=False, category="scam"):
        number, reason = normalize_number(number), _text(reason, 200)
        if type(report) is not bool:
            raise ValueError("report must be true or false")
        now = time.time()
        with self.connection() as db:
            # Reserve the write transaction before checking the per-user limit.
            # Concurrent requests must not all observe the same free slot.
            db.execute("BEGIN IMMEDIATE")
            count = db.execute("SELECT count(*) FROM personal_blocks WHERE user_id=?", (user_id,)).fetchone()[0]
            existing = db.execute("SELECT 1 FROM personal_blocks WHERE user_id=? AND number=?", (user_id, number)).fetchone()
            if count >= 1000 and not existing:
                raise ValueError("Personal block limit reached")
            db.execute("INSERT INTO personal_blocks VALUES(?,?,?,?) ON CONFLICT(user_id,number) DO UPDATE SET reason=excluded.reason", (user_id, number, reason, now))
            row = db.execute("SELECT * FROM personal_blocks WHERE user_id=? AND number=?", (user_id, number)).fetchone()
            item = self._report(db, user_id, number, category, "") if report else None
        return {"block": self.block_item(row, "personal"), "report": item}

    def unblock(self, user_id, number):
        number = normalize_number(number)
        with self.connection() as db:
            changed = db.execute("DELETE FROM personal_blocks WHERE user_id=? AND number=?", (user_id, number)).rowcount
        return {"removed": bool(changed)}

    def report(self, user_id, number, category="scam", notes=""):
        number = normalize_number(number)
        with self.connection() as db:
            return {"report": self._report(db, user_id, number, category, notes)}

    def _report(self, db, user_id, number, category, notes):
        if category not in ("scam", "spam", "other"):
            raise ValueError("category must be scam, spam, or other")
        notes = _text(notes, 500)
        # The existence check and insertion are one atomic SQLite statement.
        # Concurrent HTTP retries must return the same pending report ID.
        db.execute("""INSERT INTO reports
            SELECT ?,?,?,?,?,?,? WHERE NOT EXISTS (
                SELECT 1 FROM reports WHERE user_id=? AND number=? AND category=? AND status='pending')""",
            (str(uuid.uuid4()), user_id, number, category, notes, "pending", time.time(), user_id, number, category))
        row = db.execute("SELECT * FROM reports WHERE user_id=? AND number=? AND category=? AND status='pending'", (user_id, number, category)).fetchone()
        return self.report_item(row)

    def review_shared(self, number, reason, report_id=None):
        number, reason = normalize_number(number), _text(reason, 200)
        if not reason:
            raise ValueError("A human review reason is required")
        with self.connection() as db:
            if report_id is not None:
                report_id = _text(report_id, 100)
                row = db.execute("SELECT * FROM reports WHERE id=? AND number=?", (report_id, number)).fetchone()
                if row is None:
                    raise ValueError("Report not found for this number")
                db.execute("UPDATE reports SET status='reviewed' WHERE id=?", (report_id,))
            db.execute("INSERT INTO shared_blocks VALUES(?,?,?,?) ON CONFLICT(number) DO UPDATE SET reason=excluded.reason,report_id=excluded.report_id", (number, reason, report_id, time.time()))
            row = db.execute("SELECT * FROM shared_blocks WHERE number=?", (number,)).fetchone()
        return {"block": self.block_item(row, "shared")}

    def remove_shared(self, number):
        number = normalize_number(number)
        with self.connection() as db:
            changed = db.execute("DELETE FROM shared_blocks WHERE number=?", (number,)).rowcount
        return {"removed": bool(changed)}

    def is_blocked(self, user_id, number):
        try:
            number = normalize_number(number)
        except ValueError:
            return False  # never block anonymous/invalid caller IDs by accident
        with self.connection() as db:
            return db.execute("SELECT 1 FROM shared_blocks WHERE number=? UNION ALL SELECT 1 FROM personal_blocks WHERE user_id=? AND number=? LIMIT 1", (number, user_id, number)).fetchone() is not None


def configured_block_check(user_id, number):
    """Called off the audio/event loop. Disabled unless a shared DB is configured."""
    path = os.environ.get("CALLMA_SAFETY_DB")
    return SafetyStore(path).is_blocked(user_id, number) if path else False
