# Scam Transcript — iPhone prototype

Open **ScamTranscript.xcodeproj**, choose the **ScamTranscript** scheme and an
iPhone simulator, then Run. Select **Trained Jev v1** or **Trained Jev v2 (caller)**
in the Scorer menu. Expand **Test a typed transcript**, paste a transcript or tap
an example, then tap **Score text**. Results appear in the scrolling log.

For speech, tap **Record**, speak, then **Stop**. **Print last score** follows the
selected scorer. The menu also offers the rule baseline and original Jev behavior
model. Switching retains the recorded transcript. Typed tests are independent of
the recorded transcript. On a physical iPhone, select your development team under
Signing & Capabilities before running.

Both trained versions run offline and answer one overall scam proposition. V2
was additionally trained on caller-only turns; use `Caller:` text when possible.
Their experimental scores are calibrated on synthetic calls. Real-call accuracy
and physical-device performance remain unmeasured. These weights do not serve the
original ten behavior questions. Only one Jev checkpoint stays loaded at a time;
switching discards stale results. Trained modes use the latest 300 transcript tokens.
The three bundled checkpoints add about **1.8 GB** to the app.

## First checkout

From the repository root:

```sh
python3 ios/scripts/setup_vosk.py
python3 ios/scripts/setup_jev.py
python3 ios/scripts/setup_posttrained_jev.py
open ios/ScamTranscript.xcodeproj
```

The setup script downloads and checks SHA-256 hashes for the native library and
the English model. Both large assets are ignored by Git. They have already been
downloaded in this working copy. The Xcode project is checked in; regenerate it
with `python3 ios/scripts/generate_project.py` after adding source files.

This native SwiftUI target lives beside the existing Expo frontend. It can run
directly in Xcode without an Expo development build or a backend.

## What happens when you record

1. Ask for microphone permission and load the bundled English Vosk model on a worker queue.
2. Capture the microphone with AVAudioEngine and resample its actual hardware
   format to **16 kHz, mono, signed 16-bit PCM**.
3. Feed PCM to Vosk and show changing partials and completed transcript segments.
4. Classify the latest **180 words**, replacing partial hypotheses instead of
   appending them. A phrase is counted once per indicator in that window.
5. Print the result, rule score, indicator names, and matching phrases in the log.
6. On Stop, drain queued audio, collect Vosk's final result, and release the
   recognizer. A new recording starts with a fresh transcript window.

Audio stays in memory. There are no runtime network requests, saved recordings,
or saved transcript files. Logs retain the most recent 200 entries in memory
until the app closes. Recording stops when the app moves to the background, the
audio is interrupted, or the input route changes. A bounded work queue stops the
session with an error if recognition cannot keep up with the microphone.

## Rule baseline

The rules are in `ScamTranscript/Core/ScamClassifier.swift`. They look for
requests and surrounding pressure, not isolated words like “bank.”

| Indicator | Weight |
| --- | ---: |
| Password or PIN request | 5 |
| Verification-code request | 4 |
| Unusual payment request | 4 |
| Remote access request | 4 |
| Sensitive identity request | 3 |
| Secrecy / isolation | 2 |
| Threat or account loss | 2 |
| Pressure to stay on the line | 1 |
| Immediate action demand | 1 |

Less than three words produces “Waiting for speech.” Scores below 3 produce
“No strong indicators”; 3 or above produces “Caution.” A score of 6 or above
produces “High concern” only when a request indicator of weight 3 or higher is
present. These thresholds are provisional design choices. Scores are not
probabilities, and “No strong indicators” does not establish that a call is safe.

Negated requests such as “never share your code” are suppressed using local
context. This is an English phrase baseline: it can miss paraphrases, ASR errors,
long-range context, quotations, and scams that avoid explicit requests. It does
not identify speakers. The microphone may include both people in a conversation.
It transcribes nearby microphone audio; it does not intercept cellular call audio.

## Jev mode

Jev runs **on the phone**, using Microsoft's ONNX Runtime 1.24.3 CPU library and
the existing `verdict-151m` checkpoint. No transcript or audio is sent to a server.
The model adds approximately **578 MB** to the app; physical-device memory and
performance remain unmeasured.

The port preserves the existing Python adapter's ten behavior questions, prompt
format, 512-token bound, padding, first-three-logit interpretation, and temperature
scaling. It performs one batch for all ten questions. A native byte-level BPE
tokenizer matches the supplied Hugging Face tokenizer on the checked fixtures.

Logs show each behavior's conditional true score and its insufficient-evidence
estimate. The summary shows the strongest behavior score, **not a probability
that the call is a scam**. The current model is unvalidated for scam detection;
on the tested examples its dentist score can exceed the obvious scam score.
Parity with the existing prototype verifies integration, not semantic correctness
or scam accuracy.

Inference uses a separate worker from speech recognition. Partial transcripts
are scored at most once every three seconds; final segments and manual actions
can trigger scoring immediately. Only one model pass and the latest pending
window are retained. Switching modes or starting a fresh recording invalidates
old results. Print last score shows the last completed Jev result and requests a
fresh one when the transcript has changed. The scored transcript is printed to
make the snapshot explicit.

`setup_jev.py` reuses the local model when present, otherwise downloads the public
bundle. Model files and the ONNX Runtime download are checksum-pinned. The large
assets are ignored by Git. Sources and licenses are in `Jev-NOTICE.txt`.

## Vosk dependency provenance

- API: [alphacep/vosk-api v0.3.50](https://github.com/alphacep/vosk-api/tree/v0.3.50).
  The C header is checked in under `ScamTranscript/Bridge`.
- Native library: [santalex/libvosk v0.3.50](https://github.com/santalex/libvosk/releases/tag/v0.3.50),
  an **unofficial prebuilt distribution** of Vosk. The XCFramework contains arm64
  iPhone and arm64/x86_64 simulator slices and links Apple Accelerate and libc++.
  The maintainer documents that its iOS builds are not production-verified. This
  project tests them in the simulator and builds against the iPhone SDK; physical
  device runtime behavior still needs checking.
- Model: [vosk-model-small-en-us-0.15](https://alphacephei.com/vosk/models),
  the official small US-English model (Apache 2.0), bundled for offline use.
- License: `Vendor/VOSK-LICENSE` is included in the app bundle.

Vosk's official iOS example does not include its required library; the official
[installation page](https://alphacephei.com/vosk/install) offers that build on
request. We use the documented third-party binary so this checkout is runnable
without requesting a private build.

## Verification

Choose **Product → Test** in Xcode. The shared scheme includes:

- Rule checks for obvious scams, benign dentist/bank/payment conversations,
  negation, partial replacement, repeated phrases, and window expiration.
- Actual Vosk decoding of three **synthetic speech fixtures** at 48 kHz through
  the same resampler used for the microphone, then transcript classification and
  recognizer reset. Fixture text and provenance are under `ScamTranscriptTests/Fixtures`.
- Native/Python score parity for both post-trained models, including 300-token trimming,
  plus typed testing and stale-result suppression during model switching.
- A UI test tapping Record → Stop → Record → Stop on the simulator.
- Jev tests for exact tokenizer parity, native/Python score parity on three
  transcripts, switching over the same transcript, stale-result suppression,
  and printing the selected scorer's result. The UI test checks the scorer menu.

For unattended UI testing, grant microphone permission to the simulator app
first, or use the permission prompt on the first normal launch:

```sh
xcrun simctl privacy booted grant microphone org.scamguardian.ScamTranscript
xcodebuild -project ios/ScamTranscript.xcodeproj -scheme ScamTranscript \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' \
  -derivedDataPath ios/build -parallel-testing-enabled NO \
  CODE_SIGNING_ALLOWED=NO test
```

These tests establish prototype integration, not scam-detection accuracy.
Physical iPhone microphone quality, latency, battery use, and performance on real
held-out scam and legitimate calls remain unmeasured.

### Post-trained model integration verified October 8, 2026

Simulator and generic iPhone builds succeeded. All 16 unit/integration tests and
2 UI tests passed. Both checkpoint scores matched Python within 0.0001 on three
transcripts each, including a long transcript trimmed to 300 tokens. The UI test
selected v1 and scored a supplied example through the typed-transcript controls.
Device builds used disabled signing; running on your iPhone requires your Xcode
team. No physical-device runtime measurement was performed.
