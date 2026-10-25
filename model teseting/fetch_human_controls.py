"""Fetch bounded genuine LibriSpeech controls directly from the official archive.

Streams the gzip archive; deliberately closes the response after the first two
encountered speakers each provide >=40 s. No detector outputs affect selection.
Requires numpy and soundfile. Writes source FLACs and concatenated 40 s PCM WAVs.
"""
import hashlib
import io
import json
from pathlib import Path
import tarfile
import time
import urllib.request

import numpy as np
import soundfile as sf

BASE = Path(__file__).resolve().parent
OUT = BASE / "audio" / "human_controls"
URL = "https://www.openslr.org/resources/12/test-clean.tar.gz"
DOCS = {
    "openslr_12.html": "https://www.openslr.org/12/",
    "openslr_about.html": "https://www.openslr.org/resources/12/about.html",
}
TARGET_SECONDS = 40
SPEAKER_COUNT = 2


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    raw = OUT / "source_flac"
    raw.mkdir(exist_ok=True)
    docs = BASE / "provenance"
    docs.mkdir(exist_ok=True)
    provenance = {
        "label": "human",
        "corpus": "LibriSpeech test-clean",
        "archive_url": URL,
        "provenance_urls": list(DOCS.values()),
        "license": "CC BY 4.0",
        "human_provenance": "Official OpenSLR corpus documentation identifies these as read English speech derived from LibriVox audiobooks; corpus published in 2015, archive last modified 2017.",
        "selection": "First two speakers encountered in official tar stream; first archive-order utterances until >=40 s per speaker, concatenated then cropped at exactly 40 s. Archive order is not chronological utterance order. No detector score selection.",
        "limitations": "Read audiobook speech, with utterance joins in archive order. Two speakers are a small convenience control, not a representative phone-call false-positive benchmark. Possible training-set overlap with detector is unknown.",
        "fetched_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "speakers": [],
    }
    for filename, url in DOCS.items():
        data = urllib.request.urlopen(url, timeout=60).read()
        (docs / filename).write_bytes(data)
    speakers = {}
    with urllib.request.urlopen(URL, timeout=120) as response:
        provenance["archive_headers"] = dict(response.headers.items())
        with tarfile.open(fileobj=response, mode="r|gz") as archive:
            for member in archive:
                if not member.isfile():
                    continue
                if member.name.endswith(("SPEAKERS.TXT", "README.TXT", "LICENSE.TXT")):
                    data = archive.extractfile(member).read()
                    (docs / Path(member.name).name).write_bytes(data)
                if not member.name.endswith(".flac"):
                    continue
                speaker = Path(member.name).name.split("-")[0]
                if speaker not in speakers and len(speakers) >= SPEAKER_COUNT:
                    continue
                state = speakers.setdefault(speaker, {"samples": [], "duration": 0, "files": []})
                if state["duration"] >= TARGET_SECONDS:
                    continue
                data = archive.extractfile(member).read()
                signal, sr = sf.read(io.BytesIO(data), dtype="float32")
                assert sr == 16000 and signal.ndim == 1
                path = raw / Path(member.name).name
                path.write_bytes(data)
                state["samples"].append(signal)
                state["duration"] += len(signal) / sr
                state["files"].append({"archive_member": member.name, "path": str(path.relative_to(BASE)), "sha256": sha256(data), "sample_rate": sr, "samples": len(signal), "duration_seconds": len(signal) / sr})
                print(speaker, path.name, round(state["duration"], 3), flush=True)
                if len(speakers) == SPEAKER_COUNT and all(s["duration"] >= TARGET_SECONDS for s in speakers.values()):
                    break
    for speaker, state in speakers.items():
        audio = np.concatenate(state["samples"])[:TARGET_SECONDS * 16000]
        path = OUT / f"librispeech_test_clean_{speaker}_40s.wav"
        sf.write(path, audio, 16000, subtype="PCM_16")
        provenance["speakers"].append({"speaker_id": speaker, "label": "human", "path": str(path.relative_to(BASE)), "sha256": sha256(path.read_bytes()), "sample_rate": 16000, "channels": 1, "frames": len(audio), "duration_seconds": len(audio) / 16000, "source_duration_seconds": state["duration"], "source_files": state["files"]})
    speaker_metadata = (docs / "SPEAKERS.TXT").read_text() if (docs / "SPEAKERS.TXT").exists() else ""
    for speaker in provenance["speakers"]:
        matching = [line for line in speaker_metadata.splitlines() if line.split("|")[0].strip() == speaker["speaker_id"]]
        if matching:
            speaker["official_speaker_metadata"] = matching[0]
    (BASE / "human_control_provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    print(json.dumps(provenance["speakers"], indent=2))


if __name__ == "__main__":
    main()
