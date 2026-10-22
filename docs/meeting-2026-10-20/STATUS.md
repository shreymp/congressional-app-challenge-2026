# Meeting follow-up status

## Implemented in the review patch

- Accepted calls begin with Analyzing. Waiting for speech no longer appears as Unknown.
- Inconclusive analysis with healthy updates becomes uncertain at the 30-second boundary; stale/missing service updates still become unavailable. This is a bounded UI outcome, not a guarantee that a model can classify every caller within 30 seconds.
- The previous voice result remains visible while another window is analyzed. A service outage is still shown honestly.
- Scam risk keeps the highest observed score for each call. The label says “Highest scam risk this call”; scores reset for the next call. Live inference and service freshness remain separate from this retained historical maximum.
- The call screen uses a brighter blue background, simpler labels, animated button presses, and a fade between call and home. Reduce Motion is respected. Default tested layout fits without scrolling; overflow remains for smaller screens and accessibility text so controls cannot become unreachable.
- Demo navigation now includes Favorites and Keypad, with blocked outgoing calls and session-only favorites. Voice explanations are contextual help beside results, removed from Settings.
- Removed the update counter, technical label explanations in settings, and redundant last-update timestamp in call details. Retained meaningful caller-safety guidance.
- Common US 10-digit and +1 contact numbers match; active-call names, saved history, and favorites refresh from permitted contacts.
- Optional saved transcript excerpts are received from the authenticated agent, preserved with flagged call history, and shown only after the call. Backend option `SAVE_SCAM_TRANSCRIPTS=0` defaults off. When deliberately enabled for a previously consented controlled test, only finalized caller words from the latest 6,000 characters are sent, and only to the senior participant. The server does not save transcript files; probes never enable excerpts. This is an excerpt feature, not complete-call archiving or automatic consent.
- Applied the confirmed **callma.** name and **call with more peace of mind.** tagline across the native app and both prototypes, with vibrant colors and placeholder logos/icons. Legacy internal identifiers remain stable.
- Added two feature proposals, three long staged test scripts, a timed video plan, and a simple production call flow. Simplified the simulated frontend's flow diagram while keeping it clearly identified as a simulation.

## Validation

The counts below describe the original functionality patch. Branding, demo parity, and design validation are recorded separately in [BRAND-IMPLEMENTATION.md](BRAND-IMPLEMENTATION.md).

**56 iOS unit/UI tests passed; 26 backend tests passed; zero failures.** See `validation.json` and the adjacent logs for final counts and script word counts. The scripts contain 218, 248, and 250 spoken words; estimates at 150 words per minute are about 87, 99, and 100 seconds. Recordings have not been timed.

Automated iOS tests cover state, persistence, ordering, stale updates, scoped evidence, monotonic risk/reset, contact matching, navigation, and call controls on an iPhone simulator. Backend tests use fake rooms, simulated PCM, recognizers and scorers, plus a local HTTP test server. These tests do not establish deployed model accuracy or prove real phone calls work with this patch. Screenshot evidence is from explicit test fixtures: [call screen](call-screen-test-fixture.png) and [settings](settings-test-fixture.png).

## Still required

1. **Fix the real human voice false positive.** There is no recording of the meeting's failing human call in the supplied material, so its exact cause cannot be reproduced here. The real adapter already compares raw logits because probabilities saturate near 1; arbitrarily raising a threshold could hide AI calls too. Collect consented, separately labeled human and synthetic phone calls, replay them through `test_offline.py --phone --json-out ...`, measure false positives and misses on held-out callers, and calibrate with independent data. Do not claim the UI changes fixed model accuracy.
2. **Outgoing calls through the app.** The configured LiveKit backend is explicitly inbound-only. It has no outbound SIP trunk or authenticated dial API. A working solution needs a provisioned outbound provider/trunk, server-side authorization and number handling, room/token creation, agent dispatch, outbound caller-audio selection, and physical call testing. The patch keeps the existing mobile-service fallback; outgoing calls remain unprotected. Creating a calling UI alone would not fix routing.
3. **Automatic call-start notice and consent.** The current agent is silent and begins analysis when caller media arrives. A notice/consent design must gate analysis and excerpt delivery before processing, handle rejection/timeouts, and work on both ends. It must be tested against the actual provider's answer/ringback behavior. The disabled excerpt switch is not a consent system. Use previously consented staged calls meanwhile. See the consent note and official Illinois source in MEETING-PACK.md.
4. **New features.** The name and tagline are confirmed. The team still needs to select features. The trusted-contact shortcut and actionable warning are proposals; the guardian app remains a larger future project. No teammate decisions or contributions are invented.
5. **Live validation and deployment.** Rebuild the phone app and deploy the reviewed backend before testing this patch live. Run the three staged calls, measure first result time and duration, inspect saved history/excerpts, and test both hang-up directions. No calls or cloud deployments were performed in this session.
6. **Video and submission.** Confirm the roster, contributions, brand lettering, and full AI/tool-use disclosure. Record Friday, October 23, 4:30–7 p.m., after the Wednesday finish/Thursday testing plan. A planned script is not a finished video or a submitted entry.

## Repository handling

The current main checkout already contained modified ring-cleanup files, an edited Xcode project, untracked testing documents, and workspace settings. Their original tracked-file contents were snapshotted and fingerprinted before this patch; they were preserved. The review patch excludes those earlier changes. Azim's branch was inspected, not merged or overwritten: the transcript's main-to-Azim merge discussion ended without a final agreed method, and this work did not require editing that teammate's branch.

The root README links to the review materials. No models, tokens, credentials, private configuration, or earlier call recordings are included in the review patch. Final judge access, removal of unrelated prototypes, and branch merge remain team review decisions.
