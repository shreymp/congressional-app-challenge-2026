# Kev transcript-signal prototype

Run this folder, not the Expo repository root:

```bash
cd backend/jev-prototype
../../.venv/bin/python -m pip install -e .
../../.venv/bin/python jev_scam_signals.py --download-model
../../.venv/bin/python jev_scam_signals.py --demo
../../.venv/bin/python jev_scam_signals.py --contrast-check
```

This is the Kev layer of Scam Guardian, not a generic scam classifier. Kev sees one rolling transcript window as state and scores ten typed behavior questions against that same state: money request, credentials request, verification-code request, personal-information request, urgency, pressure, fear/threat, secrecy, unusual payment method, and impersonation. The product can explain those signals directly instead of hiding everything behind one broad "scam or not" verdict.

The prototype runs the 151M Verdict/OpenJev ONNX model locally. It sends all ten true/false/abstain questions in one ONNX batch, so the demo proves the shape of the Kev architecture: one transcript window, many independent questions, one forward pass, structured probabilities out.

`probability` means `P(true | sufficient evidence)`. `insufficient_evidence_probability` is retained separately. This project intentionally does not contain audio/deepfake code or a final scam classification decision.

The first model download is about 578 MB. The checkpoint has not been trained or calibrated on these scam-specific labels, so this is a runnable zero-shot prototype rather than a validated safety model. The honest demo claim is: pipeline proven end to end, local/on-device path proven, signal accuracy pending fine-tuning and calibration.

## Architecture notes

- State: a rolling transcript window, ideally with speaker labels such as `Caller:` and `User:`.
- Questions: ten concrete behavior propositions, phrased around what the caller is doing.
- Inference: batch all ten questions into one local ONNX call.
- Output: per-signal probability, insufficient-evidence probability, and latency telemetry.
- Scope: no audio/deepfake pipeline and no final scam decision model in this layer.

Speaker attribution is a major requirement for real use. If the user says, "I am not giving you my password," a model without speaker labels may still fire on the password signal. Training data should include hard negatives where legitimate callers mention banks, identity verification, family money requests, IT help desks, doctors' offices, and dates of birth without any scam behavior.

Keep rolling windows close to Kev's expected input length. A roughly 1,000-token window with overlap is safer than feeding an entire call, and shorter windows bound latency because the ONNX graph reads the full state every time.

Live transcripts are messy, so training and evaluation should include speech-to-text errors, missing punctuation, and misheard numbers. Clean scripted text alone will make the prototype look stronger than it is.

## Sanity check before fine-tuning

Run:

```bash
../../.venv/bin/python jev_scam_signals.py --contrast-check
```

This compares an obvious code-request scam transcript against a normal dentist scheduling transcript. In the current zero-shot checkpoint, the signals do not separate reliably; the dentist transcript can score similarly to the scam transcript. That means the architecture is wired and runnable, but the current model adapter should be treated as unvalidated until the option formatting is confirmed against Kev's training code and the model is fine-tuned/calibrated on scam-signal data.

## Training plan

- Label each transcript chunk with ten yes/no labels, one per signal.
- Use synthetic data for volume, but include hard legitimate negatives and human spot checks.
- Hold out real or realistic transcripts that the generator did not influence.
- Fine-tune Kev with LoRA using its own training path.
- Calibrate afterward with a temperature per signal on a held-out set.
- Report Brier score and expected calibration error per signal, not just accuracy.
