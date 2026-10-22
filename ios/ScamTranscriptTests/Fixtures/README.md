These are synthetic integration fixtures, generated using macOS `say` with the
Samantha voice at 145 words/minute, then converted to 48 kHz mono Int16 WAV with
`afconvert`. They test resampling, actual Vosk decoding, rule integration, and
session reset. They are not training data or an accuracy benchmark.

- scam.wav: "Tell me your verification code right now. Do not tell anyone. Stay on the line."
- dentist.wav: "Hello, this is the dentist calling to reschedule your appointment for Tuesday. Please call our office when you have time."
- bank.wav: "This is your bank. We never ask you to share your verification code. Enter the code only in the official app."
