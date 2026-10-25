#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
exec .venv/bin/python "model teseting/run_swift_checks.py"
