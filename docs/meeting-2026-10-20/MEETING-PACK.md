# October 20 meeting pack

The meeting is already happening in person, 9–11 p.m. Central. No calendar change was made.

## Three name ideas

- **CallKind** — short, friendly, and easy to say. My first choice for an app meant for older adults.
- **VoiceHarbor** — suggests a place to pause and get help when a call feels wrong.
- **CallBeacon** — suggests an early warning and a clear next step.

These are proposals for a team vote. Availability and trademark clearance have not been checked. Keep Callshield in the code until the team chooses a name.

## Two feature ideas

1. **Call someone I trust.** Save a trusted person's number. After ending a suspicious call, one large button starts a separate call to that person. Sharing a transcript stays a separate choice. This could help someone check a supposed family emergency without calling the suspicious number back.
2. **Tell me what to do.** Show one short reason and one next step, based on an actual detected signal. Example: “They asked for a security code. Hang up and call your bank using the number on your card.” Avoid a generic explanation pretending to identify a specific signal the current whole-transcript classifier does not supply.

Both are proposals, not implemented features. A guardian companion app is a later option; account linking, permission, revocation, and notifications make it a larger change than the two ideas above.

## Plan from the meeting

- Tuesday, October 20: choose a name and features; scripts and ideas ready for the meeting. The spoken “10:20” deadline is ambiguous; it may refer to the date rather than a clock time.
- Wednesday, October 21: finish app changes; review the branch and demo plan.
- Thursday, October 22: test, fix failures, and rehearse.
- Friday, October 23, 4:30–7 p.m.: record the video.
- Submission deadline in the official 2026 rules: Monday, October 26, noon Eastern / 11 a.m. Central.

## Ready-to-use materials

- [Three call scripts](CALL-SCRIPTS.md): each has over 180 spoken words; rehearse at 120–150 words per minute and use a stopwatch. The scripts are not duration-verified recordings.
- [Video script](VIDEO-SCRIPT.md): a 2:55 shot plan, using short excerpts from the longer tests.
- [Call flow](CALL-FLOW.md): simple diagram for the video and repo.
- [Implementation and test status](STATUS.md): completed work, evidence, and remaining dependencies.

## Consent for controlled tests

Before any audio is routed through the app or saved, tell each participant what will happen and get an explicit yes. Suggested wording: “This is a staged Callshield test. Your voice will be processed by our cloud services, and we may save a transcript excerpt and record the demo video. Do you agree?” Record consent separately from the scripted scam dialogue. Do not use real credentials, account numbers, payments, or a person's cloned voice without their permission.

The meeting's claim that silence automatically establishes recording consent is not a verified legal rule. Illinois law addresses consent of all parties to private conversations in its eavesdropping provisions. This pack does not establish that a notice alone meets the requirements for every call. The automatic notice and consent flow remain unfinished. Transcript excerpt delivery is therefore off by default and intended only for controlled, previously consented test calls when explicitly enabled on the server.

Sources checked October 20, 2026:
- [Official 2026 CAC rules](https://www.congressionalappchallenge.us/wp-content/uploads/2026/05/2026-CAC-Rules.pdf)
- [Illinois 720 ILCS 5/14-2](https://www.ilga.gov/documents/legislation/ilcs/documents/072000050K14-2.htm)
