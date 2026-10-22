"""Offline store tests and real local HTTP contract tests. No external messages."""
import json
import os
import concurrent.futures
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from safety_service import make_server
from safety_store import SafetyStore, normalize_number

ALICE, BOB, ADMIN = "test-alice-token-32-characters-long", "test-bob-token-32-characters-long--", "test-admin-token-32-characters-long"
ADMIN_USER = "test-ordinary-user-named-admin-32chars"
NUMBER = "+15551234567"


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "safety.sqlite3"
        self.store = SafetyStore(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_manual_block_persists_is_isolated_and_reversible(self):
        self.assertFalse(self.store.is_blocked("alice", NUMBER))
        result = self.store.block("alice", "+1 (555) 123-4567", "Manual post-call block")
        self.assertEqual(result["block"]["number"], NUMBER)
        self.assertTrue(SafetyStore(self.path).is_blocked("alice", NUMBER))
        self.assertFalse(self.store.is_blocked("bob", NUMBER))
        self.assertEqual(os.stat(self.path).st_mode & 0o777, 0o600)
        self.assertTrue(self.store.unblock("alice", NUMBER)["removed"])
        self.assertFalse(self.store.is_blocked("alice", NUMBER))

    def test_report_never_blocks_until_explicit_shared_review(self):
        report = self.store.report("alice", NUMBER)["report"]
        self.assertEqual(report["status"], "pending")
        self.assertFalse(self.store.is_blocked("alice", NUMBER))
        self.assertFalse(self.store.is_blocked("bob", NUMBER))
        repeated = self.store.report("alice", NUMBER)["report"]
        self.assertEqual(report["id"], repeated["id"])
        self.store.review_shared(NUMBER, "Reviewed enforcement evidence", report["id"])
        self.assertTrue(self.store.is_blocked("alice", NUMBER))
        self.assertTrue(self.store.is_blocked("bob", NUMBER))
        self.assertEqual(self.store.list_for_user("alice")["reports"][0]["status"], "reviewed")
        self.store.remove_shared(NUMBER)
        self.assertFalse(self.store.is_blocked("bob", NUMBER))

    def test_invalid_report_rolls_back_combined_block(self):
        with self.assertRaises(ValueError):
            self.store.block("alice", NUMBER, report=True, category="fake")
        self.assertFalse(self.store.is_blocked("alice", NUMBER))
        with self.assertRaises(ValueError):
            self.store.review_shared(NUMBER, "", None)
        with self.assertRaises(ValueError):
            self.store.review_shared(NUMBER, "Review", "missing-id")

    def test_unknown_numbers_are_never_wildcards(self):
        for number in ("", "unknown", "anonymous", "15551234567", "+1", "+15551234567 OR 1=1"):
            with self.assertRaises(ValueError):
                normalize_number(number)
            self.assertFalse(self.store.is_blocked("alice", number))

    def test_concurrent_report_retries_return_one_pending_id(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.store.report("alice", NUMBER), range(24)))
        self.assertEqual(len({r["report"]["id"] for r in results}), 1)
        self.assertEqual(len(self.store.list_for_user("alice")["reports"]), 1)
        self.assertFalse(self.store.is_blocked("alice", NUMBER))


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = SafetyStore(Path(self.temp.name) / "safety.sqlite3")
        self.server = make_server(self.store, {ALICE: "alice", BOB: "bob", ADMIN_USER: "admin"}, ADMIN, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        self.temp.cleanup()

    def request(self, method, path, body=None, token=ALICE):
        request = urllib.request.Request(self.url + path, method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json", **({"Authorization": "Bearer " + token} if token else {})})
        try:
            with urllib.request.urlopen(request, timeout=3) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as response:
            with response:
                return response.code, json.load(response)

    def test_authenticated_personal_block_contract(self):
        self.assertEqual(self.request("GET", "/v1/blocks", token=None)[0], 401)
        self.assertEqual(self.request("GET", "/v1/blocks", token="wrong")[0], 401)
        status, result = self.request("POST", "/v1/blocks", {"number": NUMBER, "report": True})
        self.assertEqual(status, 201)
        self.assertEqual(result["report"]["status"], "pending")
        self.assertEqual(self.request("GET", "/v1/blocks")[1]["blocks"][0]["scope"], "personal")
        self.assertEqual(self.request("GET", "/v1/blocks", token=BOB)[1], {"blocks": [], "reports": []})
        self.assertEqual(self.request("DELETE", "/v1/blocks/%2B15551234567")[1], {"removed": True})

    def test_shared_list_requires_separate_admin_review(self):
        report = self.request("POST", "/v1/reports", {"number": NUMBER})[1]["report"]
        body = {"number": NUMBER, "reason": "Human review", "reportId": report["id"]}
        self.assertEqual(self.request("POST", "/v1/admin/shared-blocks", body)[0], 401)
        self.assertEqual(self.request("POST", "/v1/admin/shared-blocks", body, ADMIN)[0], 201)
        self.assertEqual(self.request("GET", "/v1/blocks", token=BOB)[1]["blocks"][0]["scope"], "shared")
        self.assertEqual(self.request("DELETE", "/v1/blocks/%2B15551234567", token=BOB)[1], {"removed": False})
        self.assertTrue(self.store.is_blocked("bob", NUMBER))
        self.assertEqual(self.request("DELETE", "/v1/admin/shared-blocks/%2B15551234567", token=ADMIN)[1], {"removed": True})
        self.assertFalse(self.store.is_blocked("bob", NUMBER))

    def test_input_validation_does_not_create_block(self):
        for body in ({}, {"number": "unknown"}, {"number": NUMBER, "report": "true"}, {"number": NUMBER, "reason": "x" * 201}):
            self.assertEqual(self.request("POST", "/v1/blocks", body)[0], 400)
        self.assertEqual(self.request("POST", "/v1/blocks", {"number": NUMBER, "reason": "x" * 5000})[0], 413)
        self.assertEqual(self.request("GET", "/v1/blocks")[1]["blocks"], [])

    def test_user_named_admin_has_an_independent_mutation_limit(self):
        for _ in range(30):
            self.assertEqual(self.request("POST", "/v1/reports", {"number": NUMBER}, token=ADMIN_USER)[0], 201)
        self.assertEqual(self.request("POST", "/v1/reports", {"number": NUMBER}, token=ADMIN_USER)[0], 429)
        self.assertEqual(self.request("POST", "/v1/admin/shared-blocks", {"number": NUMBER, "reason": "Reviewed"}, token=ADMIN_USER)[0], 401)
        self.assertEqual(self.request("POST", "/v1/admin/shared-blocks", {"number": NUMBER, "reason": "Reviewed"}, token=ADMIN)[0], 201)


if __name__ == "__main__":
    unittest.main()
