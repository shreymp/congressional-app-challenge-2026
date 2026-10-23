"""Quick fallback core regression checks; no neural-model accuracy claims."""
from pathlib import Path
import json
import os
import subprocess
import sys
import time

root = Path(__file__).resolve().parent
python = root.parent / ".venv/bin/python"
runs = []
for version in ("baseline", "current"):
    directory = root / "snapshots" / version
    checks = ["test_integration"] if version == "baseline" else ["test_cumulative", "test_integration"]
    for check in checks:
        # The source path is flattened. Rebind only its read-only fixture location.
        code = ("import pathlib,sys,unittest;sys.path.insert(0," + repr(str(directory)) + ");"
                "import " + check + " as m;"
                + ("m.FIXTURE=pathlib.Path(" + repr(str(directory / "ios/CallshieldTests/Fixtures/deepfake-wire.json")) + ");" if check == "test_integration" else "")
                + "r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(m));sys.exit(not r.wasSuccessful())")
        command = [str(python), "-c", code]
        start = time.perf_counter()
        result = subprocess.run(command, text=True, capture_output=True)
        log = root / "logs" / f"fallback_{version}_{check}.txt"
        log.write_text("Command: " + repr(command) + "\n\n" + result.stdout + result.stderr + f"\nExit code: {result.returncode}\n")
        runs.append(dict(version=version, check=check, exit_code=result.returncode, elapsed_sec=time.perf_counter()-start, log=str(log.relative_to(root))))
    # test_offline.py is a CLI runner, not a unittest module. Exercise its wiring
    # explicitly with a seeded STUB; this is separate from the actual model benchmark.
    offline = directory / "test_offline.py"
    audio = root / "audio/human_controls/librispeech_test_clean_6930_40s.wav"
    out = root / "results" / f"fallback_{version}_offline_stub_wire.json"
    code = ("import random,runpy,sys;random.seed(20261022);sys.path.insert(0," + repr(str(directory)) + ");"
            "sys.argv=[" + repr(str(offline)) + "," + repr(str(audio)) + ",'--json-out'," + repr(str(out)) + "];runpy.run_path(" + repr(str(offline)) + ",run_name='__main__')")
    command = [str(python), "-c", code]
    env = dict(os.environ, DETECTOR="stub")
    start=time.perf_counter();result=subprocess.run(command,env=env,text=True,capture_output=True)
    log=root/"logs"/f"fallback_{version}_test_offline_stub.txt"
    log.write_text("STUB plumbing check; not model accuracy or human false-positive evidence.\nCommand: DETECTOR=stub " + repr(command) + "\n\n" + result.stdout + result.stderr + f"\nExit code: {result.returncode}\n")
    runs.append(dict(version=version,check="test_offline_stub",exit_code=result.returncode,elapsed_sec=time.perf_counter()-start,log=str(log.relative_to(root))))
(root/"results/fallback_regressions.json").write_text(json.dumps(runs,indent=2)+"\n")
print(json.dumps(runs,indent=2))
sys.exit(any(r["exit_code"] for r in runs))
