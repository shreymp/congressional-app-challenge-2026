#!/usr/bin/env python3
"""Bundle the two locally trained call classifiers; no network requests."""
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKPOINTS = [
    ('V1', 'call-v1', 'c0ea817140c391afba796cff9bed9ac7025e86ff1c35708d8492706539aaddef'),
    ('V2', 'call-v2-caller', '8f7bbb21ce135765d4de33d7fc3f5947d31826424249018a6671d0b611541c8a'),
]
for version, name, expected in CHECKPOINTS:
    source = ROOT / 'backend/jev-posttrain/runs' / name
    destination = ROOT / 'ios/ScamTranscript/Resources' / ('JevCall' + version)
    model = source / 'model.onnx'
    digest = hashlib.file_digest(model.open('rb'), 'sha256').hexdigest()
    if digest != expected:
        raise ValueError(f'Unexpected checkpoint hash: {model}')
    temperature = json.loads((source / 'evaluation.json').read_text())['models']['candidate']['validation_temperature']
    destination.mkdir(parents=True, exist_ok=True)
    for filename in ['model.onnx', 'tokenizer.json']:
        shutil.copy2(source / filename, destination / filename)
    (destination / 'calibration.json').write_text(json.dumps({'temperature': temperature}, indent=2) + '\n')
    print(f'Bundled {name}: {digest}')
