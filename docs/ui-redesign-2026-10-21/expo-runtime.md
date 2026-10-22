# Legacy Expo call screen — October 21, 2026

Interactive checks used Expo Go 57.0.9 in the existing iOS 26.5 simulator, `10469AE2-2454-4954-913E-A1100BE59050` (Callshield Oct 19 Automated), at its existing display and default text settings. This is a simulated interface, with no connected audio, calls or messages.

## Observed

- The active call has a fixed dark screen, lowercase `callma.`, caller/number/timer, and an explicit simulated-call disclosure. Normal app tabs/header are absent. Content respects the visible top and bottom safe areas.
- Voice and Words open one anchored panel at a time without shifting caller, analysis buttons, mute/speaker or End Call. End remains visible and accessible.
- Close dismisses the panel; selecting the other analysis button replaces its content.
- Mute and speaker visibly toggle local demo state; keypad remains disabled.
- End returns to the existing Protect dashboard. Start demo reenters the fixed screen with timer and toggles reset.

Runtime inspection found the original panel note clipped. The retained App.js fix gives the panel an explicit measured height, keeps its heading outside a `flex: 1, minHeight: 0` ScrollView, and uses concise complete copy. After restarting Metro with a cleared cache, **all final Voice and Words text fits visibly** at the tested size, including unknown-evidence, identity, illustrative-score and no-analysis/no-messages disclosures. Original coordinate drag/scroll attempts did not establish access to the clipped note; the final default-size acceptance is based on complete visible text, not a claimed scrolling pass.

Evidence: `expo-active.png`, `expo-controls-selected.png`, `expo-ended.png`, `expo-reentered.png`, `expo-voice-final.png`, `expo-words-final.png`. Earlier `expo-voice.png` / `expo-words.png` show the pre-fix issue.

## Checks and limits

- Final App.js parsed successfully with installed `@babel/parser` (JSX). Final `git diff --check -- frontend/App.js` passed.
- Prior iOS/Android offline exports passed October 20 (see `docs/RESUME-guardian-2026-10-20.md`). No exports were repeated today. Final panel refinement was exercised in a fresh iOS Metro bundle, not a new Android export.
- No lint/test script or ESLint exists in this frontend. React DOM / React Native Web are absent; no dependencies were installed for web testing.
- Compact displays, larger accessibility text, VoiceOver and Android interaction remain unverified. A `<700`-point compact branch exists but is not runtime evidence. The bounded ScrollView is intended for overflow; scrolling with large text remains a separate check.
- Expo logs a SafeAreaView deprecation warning; default iOS safe areas were visibly respected. Android edge-to-edge safe areas need device testing before treating this legacy preview as a shipped client.
- Initial loopback failure was infrastructure: Metro listened on `[::1]` while the manifest pointed at `127.0.0.1`. Setting `REACT_NATIVE_PACKAGER_HOSTNAME=localhost` fixed the manifest and runtime connection. Log: `expo-metro.log`.

## Task processes

Only this task's local Metro instances were started/stopped: session 3456 / PID 78393, session 88427 / PID 79099, and final session 32291 / PID 81756 (port 8094). The final instance was stopped after validation. The preexisting port 8084 service was untouched. No deployment, real calls or messages occurred.
