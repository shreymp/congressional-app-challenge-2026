# Guardian / Expo checkpoint — paused October 20, 2026

User paused all work to sleep. Do not resume feature work, research, tests or builds without user instruction.

## Latest Expo change

- Only `frontend/App.js` changed for this task. Other existing dashboard pages are preserved.
- Active simulated calls now bypass the app header/tabs and use a fixed dark Phone-style caller screen with lowercase `callma.` branding and explicit simulation disclosure.
- Voice and Words buttons toggle one anchored analysis panel; it occupies only the region above the call controls and does not shift layout. The panel can scroll internally if needed; the call screen itself does not scroll.
- Mute/speaker change local demo state only; keypad is disabled; red End Call returns to the existing Protect page, whose Start Demo action reenters the call screen. No audio, messages, real calls or reports were added.
- Last refinement moved the absolute panel into the full top-region parent so its interactive area remains inside that parent's bounds on Android as well as iOS.
- Required exact Expo 57 documentation was read before code: https://docs.expo.dev/versions/v57.0.0/. Apple Design references were applied.

## Completed checks / processes

- Final Babel JSX parse passed using installed `@babel/parser`.
- Final offline export completed with exit 0: `CI=1 EXPO_OFFLINE=1 ./node_modules/.bin/expo export --platform ios --platform android --output-dir /private/tmp/callma-expo-fixed-call --max-workers 2` (from `frontend`). Android: 580 modules; iOS: 582 modules; both Hermes bundles about 1.5 MB. Artifacts remain at `/private/tmp/callma-expo-fixed-call`.
- The final export tool session was **27597**. At pause, a stop request returned its already-completed exit-0 result. No active process remains from this agent.
- Earlier export session **77088** also completed exit 0. No Expo development server was started.
- `git diff --check -- App.js` passed before the final small panel-parent refinement; that final refinement parsed and exported successfully, but a new whitespace check was not run after the user paused.
- Frontend has no lint/test scripts or installed ESLint. `react-native-web` and `react-dom` are absent; no web export was attempted or dependencies installed.
- Two early ad hoc Babel-transform commands failed because of module paths/preset resolution. The corrected direct Babel JSX parse and actual Expo native exports passed.

## Pending after explicit resume

- Optional final whitespace check of `frontend/App.js`.
- Interactive Expo verification of toggle/dismiss, End Call/Start Demo reentry, smaller displays, largest text sizes, and safe areas. Native exports establish compilation, not runtime/visual verification. No simulator/physical-device interaction was performed for this Expo screen.
- Summarize the narrow Expo change to the parent/user. No additional redesign is planned.

## Existing native / audit evidence

- Native guardians, reviewed message sharing, manual blocks/reports, local persistence and authenticated safety-service integration are implemented. Never send real test messages or calls.
- `docs/features-2026-10-20/native.md` records functionality and limits; initial suite passed 32 tests.
- Final native review passed **42 tests, 0 failures/skips**: `docs/features-2026-10-20/native-final-review-summary.json` and `native-final-review-tests.log`.
- Final international-number regression rerun passed **1 test, 0 failures**: `native-international-final-summary.json` and `native-international-final-tests.log` in the same directory.
- Native fixes include serialized safety changes, honest offline report errors, exact international-number comparison, and no-score `insufficient_evidence` support. UI agent owns the production active-call layout and its tests.
- Read-only transcript data audit is saved in `docs/testing/2026-10-20-transcript/extended-data-audit.json`: checked overlap counts, file checksums, four positive script-group sizes and within-test shared-speaker dependence. No raw transcripts or training were added by this agent.

No files were reverted, committed or pushed. Existing logs and artifacts are preserved.
