"""Build the fixed announcement with eSpeak NG and SoX; never runs during a call."""
import argparse
from pathlib import Path
import subprocess
import tempfile

TEXT = "This call is being recorded."


def generate(output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        raw = str(Path(folder) / "notice.wav")
        subprocess.run(["espeak-ng", "-v", "en-us", "-s", "165", "-w", raw, TEXT], check=True)
        subprocess.run(["sox", raw, "-r", "16000", "-c", "1", "-b", "16",
                        "-e", "signed-integer", str(output)], check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    generate(parser.parse_args().output)
