"""Reproduce local contract checks; these do not measure deployed model quality."""
from pathlib import Path
from datetime import datetime, timezone
import json
import os
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent / 'logs'
PYTHON = os.environ.get('CALLSHIELD_TEST_PYTHON', sys.executable)
LIVE = 'backend/AI Deepfake Pipeline/LiveKit Setup'
SUITES = [
    ('transcript', LIVE, [PYTHON, '-m', 'unittest', '-v', 'test_transcript_pipeline']),
    ('worker-integration', '.', [PYTHON, '-m', 'unittest', 'discover', '-s', LIVE, '-p', 'test*integration.py', '-v']),
    ('tester-tools', '.', [PYTHON, '-m', 'unittest', 'discover', '-s', 'scripts', '-p', 'test_*.py', '-v']),
    ('ring-lifecycle', LIVE, [PYTHON, 'test_senior_ring.py']),
    ('transcript-service', 'backend/Transcript-Based Detector', [PYTHON, '-m', 'unittest', '-v', 'test_model_service']),
    ('node-connector', 'backend/Transcript-Based Detector', ['node', '--test']),
    ('cloud-contracts', 'deploy/livekit', [PYTHON, '-m', 'unittest', '-v', 'test_cloud', 'test_probe_checks']),
]

if __name__ == '__main__':
    OUT.mkdir(exist_ok=True)
    results = []
    for name, cwd, command in SUITES:
        started = datetime.now(timezone.utc).isoformat()
        before = time.monotonic()
        try:
            run = subprocess.run(command, cwd=ROOT / cwd, capture_output=True, text=True, timeout=240)
            code, output = run.returncode, run.stdout + run.stderr
        except subprocess.TimeoutExpired:
            code, output = 124, 'Timed out after 240 seconds.'
        output = re.sub(r'eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+', '[REDACTED JWT]', output)
        (OUT / f'{name}.log').write_text(f'Started UTC: {started}\nExit: {code}\n' + output)
        result = dict(suite=name, started_utc=started, exit_code=code, seconds=round(time.monotonic()-before, 2))
        results.append(result)
        (OUT / 'backend-summary.json').write_text(json.dumps(results, indent=2)+'\n')
        print(json.dumps(result), flush=True)
