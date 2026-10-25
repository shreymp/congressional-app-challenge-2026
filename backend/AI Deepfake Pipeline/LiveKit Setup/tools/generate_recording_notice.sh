#!/bin/sh
# macOS system voice, local generation only. Review intelligibility before live deployment.
set -eu
base=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
mkdir -p "$base/assets"
say -v Samantha -r 155 -o "$work/notice.aiff" 'This call is being recorded.'
afconvert -f WAVE -d LEI16@16000 -c 1 "$work/notice.aiff" "$base/assets/recording_notice.wav"
