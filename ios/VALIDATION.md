# Prototype validation — October 2, 2026

Environment: Xcode 26.6 (17F113), iPhone 17 Pro simulator, iOS 26.5,
Apple Silicon. Final simulator results are in the locally generated,
Git-ignored `TestResults/Simulator-Final.xcresult`.

For the initial rule-only build, **11 tests passed, zero failures:** eight rule/window tests, two Vosk tests,
and one recording UI test. The UI test starts/stops recording twice through
the real AVAudioEngine input path. Microphone permission was granted to the
simulator before unattended testing.

Actual Vosk outputs from synthetic WAV files, resampled from 48 kHz to 16 kHz:

| Fixture | Recognized transcript | Rule result |
| --- | --- | --- |
| Scam | tell me your verification code right now do not tell anyone stay on the line | High concern |
| Dentist | hello this is the dentist calling to reschedule your appointment for tuesday please call our office when you have time | No strong indicators |
| Bank | this is your bank we never ask you to share your verification code enter the code only in the official app | No strong indicators |

The integration test checks streaming partials, final text, classification, and
fresh recognizer state across all three fixtures. Another test verifies that an
incorrect input PCM format is rejected. Synthetic examples are pipeline checks;
they do not establish real-world accuracy.

The final source also builds successfully for `generic/platform=iOS` with
signing disabled. This verifies the iPhone SDK and arm64 library link. Installation
and execution on a physical iPhone require the user's development team and device.
No physical-device latency, memory, battery, or real-call accuracy measurements
were made. Simulator fixture processing times must not be used as iPhone claims.

The app was installed and launched in the simulator. A screenshot of its simple
record button and logs is in the local `TestResults/app-ready.png`.

## Jev switch update

The updated app passes **15 tests, zero failures**, and builds successfully for
both the simulator and generic iPhone destination. The latest test report is
`build/Logs/Test/Test-ScamTranscript-2026.10.02_15-42-28--0500.xcresult`.

Four additional tests verify:

- 36 native tokenizer vectors exactly match the existing Hugging Face tokenizer,
  including all ten question prompts, Unicode, special tokens, and long text.
- Ten native Jev signal probabilities and abstention estimates match the existing
  Python adapter within 0.0001 on three transcripts, including the user's
  “gimme your social security number” transcript.
- Switching a populated transcript to Jev produces actual model results and the
  score button prints them; switching back prints the rule result for that text.
- Switching back while inference is running suppresses the old Jev result.

The UI test also taps Use Jev → Use rules and checks the button changes modes.
The inference runs on the simulator using Microsoft's ONNX Runtime 1.24.3 CPU
library, without a backend. Python reference scores use ONNX Runtime 1.30.0.

Parity is not model-quality validation: the existing adapter's strongest signal
on the dentist example is higher than on the obvious code-request scam. This
implementation preserves that adapter's semantics and labels Jev experimental.
Its percentages describe behavior scores, not calibrated scam probabilities.
Physical iPhone runtime and memory performance remain untested.
