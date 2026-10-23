"""Public recordings -> the SAME small Vosk model used by the app.

Only local research files; no microphone, calls, or messages are opened.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import wave
from pathlib import Path

from vosk import Model, KaldiRecognizer, SetLogLevel

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", type=Path, default=HERE / "data/real_calls")
    args = p.parse_args()
    output = args.data / "audio"
    output.mkdir(parents=True, exist_ok=True)
    source = [("HlTpousFPsM", Path("/tmp/callshield-ftc-amazon.wav")),
              ("8sT121uUFOo", Path("/tmp/callshield-ftc-8sT121uUFOo.wav")),
              ("IQyu_yFqWGA", Path("/tmp/callshield-ftc-IQyu_yFqWGA.wav"))]
    probes = []
    for identity, path in source:
        target = output / f"{identity}.wav"
        shutil.copyfile(path, target)
        probes.append({"id": "youtube:" + identity, "path": str(target), "label": 1,
                       "source": "ftc_youtube_recording", "url": "https://www.youtube.com/watch?v="+identity,
                       "label_quality": "FTC_publicly_identified_scam", "independence": "development_probe; related scripts occur in NCSU training"})
    hvb = [json.loads(line) for line in (args.data / "hvb/probes.jsonl").read_text().splitlines()]
    for r in hvb[:3]:
        probes.append({**r, "path": str(args.data / "hvb" / (r["id"].split(":")[1] + ".wav")),
                       "reference_text": r["text"]})
    SetLogLevel(-1)
    model = Model(str(ROOT / "ios/ScamTranscript/Resources/vosk-model-small-en-us-0.15"))
    rows = []
    for probe in probes:
        path = Path(probe["path"])
        pcm = output / (path.stem + "-16k.wav")
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(path), "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(pcm)], check=True)
        recognizer = KaldiRecognizer(model, 16000)
        words, prefixes = [], []
        with wave.open(str(pcm)) as wav:
            duration = wav.getnframes()/wav.getframerate()
            count = 0
            while chunk := wav.readframes(8000):
                count += 1
                if recognizer.AcceptWaveform(chunk):
                    words.append(json.loads(recognizer.Result()).get("text", ""))
                if count % 20 == 0:
                    partial = json.loads(recognizer.PartialResult()).get("partial", "")
                    prefixes.append({"seconds": count/2, "text": "Caller: " + " ".join(words + [partial]).strip()})
            words.append(json.loads(recognizer.FinalResult()).get("text", ""))
        rows.append({**probe, "text": "Caller: " + " ".join(words).strip(), "prefixes": prefixes,
                     "duration_sec": duration, "audio_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                     "asr": "vosk-model-small-en-us-0.15; 16kHz mono PCM"})
        print(json.dumps({"id": probe["id"], "duration_sec": duration, "words": len(rows[-1]["text"].split())}), flush=True)
    (args.data / "audio_probes.jsonl").write_text("".join(json.dumps(r)+"\n" for r in rows))


if __name__ == "__main__":
    main()
