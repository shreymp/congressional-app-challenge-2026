#!/usr/bin/env python3
"""Reproduce Foundation contract checks against immutable source snapshots."""
from pathlib import Path
import json
import subprocess

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "cache" / "swift"
CACHE.mkdir(parents=True, exist_ok=True)
records = []

def run(name, argv):
    p = subprocess.run(list(map(str, argv)), text=True, capture_output=True, timeout=120)
    (ROOT / "logs" / (name + ".txt")).write_text("Command: " + repr(list(map(str, argv))) + "\n\n" + p.stdout + p.stderr + f"\nExit code: {p.returncode}\n")
    records.append({"check": name, "exit_code": p.returncode, "stdout": p.stdout, "stderr": p.stderr})
    if p.returncode:
        raise SystemExit(p.returncode)

for version in ("baseline", "current"):
    ios = ROOT / "snapshots" / version / "ios"
    app = ios / "Callshield"
    src = [app / "Core/CallModels.swift", app / "Production/DeepfakeAssessment.swift"]
    executable = ROOT / "cache" / ("wire_" + version)
    run("swift_wire_compile_" + version, ["swiftc", "-module-cache-path", CACHE, *src, ROOT / "check_wire_fixtures.swift", "-o", executable])
    run("swift_wire_" + version, [executable, ios / "CallshieldTests/Fixtures/deepfake-wire.json"])

ios = ROOT / "snapshots/current/ios"
app = ios / "Callshield"
executable = ROOT / "cache/check_deepfake_contract"
src = [app / "Core/CallModels.swift", app / "Production/PhoneModels.swift", app / "Production/DeepfakeAssessment.swift", app / "Production/PhoneSessionState.swift", ios / "scripts/check_deepfake_contract.swift"]
run("swift_compile", ["swiftc", "-module-cache-path", CACHE, *src, "-o", executable])
run("swift_contract", [executable, ios / "CallshieldTests/Fixtures/deepfake-wire.json"])
run("swift_version", ["swiftc", "--version"])
run("xcode_version", ["xcodebuild", "-version"])
(ROOT / "results/swift_checks.json").write_text(json.dumps(records, indent=2) + "\n")
