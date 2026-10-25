#!/usr/bin/env python3
"""Bounded mocked-agent/notice regressions; no service connections or real inference."""
from pathlib import Path
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
records = []
for version, module in [("baseline", "test_agent_integration"), ("current", "test_agent_integration"), ("current", "test_recording_notice")]:
    snapshot = ROOT / "snapshots" / version
    code = "import sys,unittest;sys.path.insert(0," + repr(str(snapshot)) + ");import " + module + " as m;r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(m));sys.exit(not r.wasSuccessful())"
    cmd = [sys.executable, "-c", code]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
        result = {"version": version, "module": module, "exit_code": p.returncode, "stdout": p.stdout, "stderr": p.stderr}
    except subprocess.TimeoutExpired as e:
        result = {"version": version, "module": module, "exit_code": None, "timeout_sec": 45, "stdout": (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else e.stdout, "stderr": (e.stderr or b"").decode() if isinstance(e.stderr, bytes) else e.stderr}
    log = "Command: " + repr(cmd) + "\n\n" + (result.get("stdout") or "") + (result.get("stderr") or "") + "\nResult: " + str(result.get("exit_code")) + "\n"
    (ROOT / "logs" / (version + "_" + module + ".txt")).write_text(log)
    records.append(result)
    (ROOT / "results/agent_checks.json").write_text(json.dumps(records, indent=2) + "\n")
print(json.dumps([{k: v for k, v in x.items() if k not in ("stdout", "stderr")} for x in records], indent=2))
sys.exit(any(x["exit_code"] != 0 for x in records))
