import importlib.util
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location("mac_call_test", Path(__file__).with_name("mac_call_test.py"))
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


class HandoffTests(unittest.TestCase):
    def test_config_preserves_signing_and_replaces_all_active_duplicates(self):
        old = "// CALLSHIELD_LOBBY_TOKEN = example\nDEVELOPMENT_TEAM = TEAM123\nCALLSHIELD_LOBBY_TOKEN = old\nCALLSHIELD_LOBBY_TOKEN = duplicate\n"
        result = helper.set_xcconfig(old, {"CALLSHIELD_LOBBY_TOKEN": "new-token"})
        self.assertIn("DEVELOPMENT_TEAM = TEAM123", result)
        self.assertIn("// CALLSHIELD_LOBBY_TOKEN = example", result)
        self.assertEqual(result.count("CALLSHIELD_LOBBY_TOKEN = new-token"), 1)
        self.assertNotIn("old", result)
        self.assertNotIn("duplicate", result)

    def test_config_rejects_expansion_comments_and_newlines(self):
        for value in ("a\nb", "a\rb", "wss://host", "$(SECRET)"):
            with self.assertRaises(ValueError):
                helper.set_xcconfig("", {"TOKEN": value})

    def test_host_accepts_only_expected_websocket_project_address(self):
        self.assertEqual(helper.project_host("wss://project.livekit.cloud/"), "project.livekit.cloud")
        self.assertEqual(helper.project_host("project.livekit.cloud"), "project.livekit.cloud")
        for value in ("https://project.livekit.cloud", "wss://user:password@project.livekit.cloud", "project.livekit.cloud/path", "project.livekit.cloud?token=secret", "YOUR-PROJECT.livekit.cloud", ""):
            with self.assertRaises(ValueError, msg=value):
                helper.project_host(value)

    def test_cloud_commands_route_to_hosted_probe_and_optional_simulator_invite(self):
        for command in ("cloud-probe", "full-call"):
            with patch.object(helper, "require_credentials"), patch.object(helper, "run") as run:
                helper.cloud_probe(SimpleNamespace(command=command, wav=None, timeout=180))
                args = run.call_args.args[0]
                self.assertIn(helper.ROOT / "deploy/livekit/probe.py", args)
                self.assertIn(helper.ROOT / "ios/ScamTranscriptTests/Fixtures/bank.wav", args)
                self.assertEqual("--ring" in args, command == "full-call")

    def test_private_files_have_restricted_permissions_even_when_replaced(self):
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / "configuration"
            file.write_text("old")
            file.chmod(0o644)
            helper.private_write(file, "secret")
            self.assertEqual(file.read_text(), "secret")
            self.assertEqual(stat.S_IMODE(file.stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()

