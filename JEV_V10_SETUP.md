# Install Jev V10 on another computer

V10 is now distributed as a GitHub release asset, including the exact training checkpoint (`model.safetensors`), an ONNX inference export, tokenizer, model configuration, calibration metadata, and checksums. Large weights stay outside Git history. The download is approximately **1.13 GB**; allow **4 GB free disk space** during installation.

## Install

Clone this private repository, or pull its `main` branch in a clean checkout. From the repository root, run:

```sh
python3 scripts/setup_jev_v10.py
```

The script uses an existing GitHub CLI/Git HTTPS login or `GH_TOKEN`/`GITHUB_TOKEN` with repository read access. It never prints or saves credentials. For browser-only access, download `jev-call-v10.zip` from the [V10 release](https://github.com/shreymp/congressional-app-challenge-2026/releases/tag/jev-call-v10), then run:

```sh
python3 scripts/setup_jev_v10.py --archive ~/Downloads/jev-call-v10.zip
```

Installation verifies the ZIP and every model file. It installs atomically into `backend/jev-posttrain/runs/call-v10-github`, preserving all older checkpoints. Running setup again verifies and reuses that exact bundle. A pre-existing mismatched destination causes an error instead of overwriting files; use `--destination` for a separate directory.

## Use V10 for local transcript inference

Python 3.11 or newer is recommended. In a virtual environment:

```sh
python3 -m venv .venv-v10
```

macOS/Linux:

```sh
source .venv-v10/bin/activate
```

Windows PowerShell:

```powershell
.venv-v10\Scripts\Activate.ps1
```

Then:

```sh
python -m pip install numpy tokenizers onnxruntime
python scripts/run_jev_v10.py
```

This explicitly loads **V10** and serves the existing transcript API on `127.0.0.1:8000`. Point the local transcript pipeline at that address as usual. Stop any older local model server using this port first. This does not deploy a cloud service or change a running server. Existing scripts that select V1/V2 retain their versions; use this V10 launcher to select the new model.

For a single text check:

```sh
python scripts/run_jev_v10.py --text "This is a reminder about your appointment tomorrow."
```

For a custom installation location, pass the same directory to setup's `--destination` and the launcher's `--model-dir`.

## Checkpoint and inference scope

The install directory also contains the original Hugging Face configuration and safetensors weights for continued research training; training requires the separate GLiClass/PyTorch training environment. No training data or protected evaluation sets are included.

The ONNX export was compared with the original V10 PyTorch checkpoint on three authored synthetic batches, including batch sizes one and two and a longer input. Maximum absolute logit difference: **0.0000190735**. This is export verification, not a new accuracy benchmark.

The launcher uses the existing **last 300 context tokens** scoring adapter. It reports context coverage and an experimental risk score; it does not set a scam-alert threshold. This is different from the equal-length multi-window research evaluation, so research benchmark results do not establish the launcher's live-call accuracy. Frozen temperature metadata does not establish field probability calibration. Independent human-reviewed field accuracy remains unestablished; no 95% claim is made. Existing research and source-license restrictions still apply.

Exact asset and per-file hashes are pinned in `backend/jev-posttrain/v10_release.json`.
