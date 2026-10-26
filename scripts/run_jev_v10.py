#!/usr/bin/env python3
"""Run the pinned V10 checkpoint locally; no cloud deployment or automatic threshold."""
import argparse
import importlib.util
import json
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-dir', type=Path, default=ROOT / 'backend/jev-posttrain/runs/call-v10-github')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--text', help='Score text once instead of starting the local server')
    args = parser.parse_args()
    manifest = json.loads((ROOT / 'backend/jev-posttrain/v10_release.json').read_text())
    spec = importlib.util.spec_from_file_location('jev_model_service', ROOT / 'backend/Transcript-Based Detector/model_service.py')
    service = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(service)
    with tempfile.TemporaryDirectory(prefix='jev-v10-manifest-') as temporary:
        bundle = Path(temporary) / 'manifest.json'
        bundle.write_text(json.dumps([manifest['bundle']]))
        try:
            model = service.CallModel(args.model_dir, 'V10', bundle_manifest=bundle, context_mode='tail')
        except FileNotFoundError:
            parser.exit(1, 'Install V10 first: python3 scripts/setup_jev_v10.py\n')
    if args.text is not None:
        print(json.dumps(model.assess(args.text), indent=2))
    else:
        server = service.make_server(model, args.port)
        print(f'V10 ready at http://127.0.0.1:{args.port}; experimental risk score, no field calibration.', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()


if __name__ == '__main__':
    main()
