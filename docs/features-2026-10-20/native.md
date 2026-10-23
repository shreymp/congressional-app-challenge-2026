# callma. native guardian and blocking features

Implemented October 20, 2026. These changes build on the existing SwiftUI production app without replacing its call transport or saved history.

## Implemented flows

- **Trusted guardians:** Contacts opens with a dedicated guardian section, available even without Contacts permission. Add a name and international number, or choose an allowed contact. Duplicate numbers update the existing guardian. Removal requires confirmation. Guardians persist in a protected, backup-excluded local file.
- **Contact a guardian:** The in-call action opens a recipient picker and complete message preview. A transcript excerpt is excluded by default and can be included only when an actual excerpt exists. Messages opens with the selected guardian and reviewed text; the user must tap Send. The system share sheet is available when Messages cannot send. Adding a guardian does not contact anyone or share calls.
- **Manual blocks and reports:** After a call, its details offer Block for Me, Block and Report, or Report for Review. Local blocks take effect for callma. incoming events on this iPhone and survive restarts. Reports alone do not create a block. No detection score calls a blocking or reporting method.
- **Server sync:** The app uses the authenticated safety-service endpoints implemented alongside this work. An explicit offline Block and Report action is queued and retried when connected. Report for Review alone requires a connection and shows a failure if unavailable. A server failure never displays a successful unblock; the existing block remains. Personal and reviewed community blocks appear separately in Settings.
- **Honest score wording:** Transcript warning copy and the warning boolean use the requested 0.75 experimental threshold. Scores are described as scores out of 100, with a limitation, rather than confirmed scam probabilities. Voice analysis retains a separate optional score for the in-call guidance UI.
- **Insufficient evidence:** The native transcript contract accepts `insufficient_evidence`, displays that there is not enough context, and discards any numeric score attached to that state. It does not treat abstention as a low scam score or a positive warning.

## Server contract

`GET /v1/blocks`, `POST /v1/blocks`, `DELETE /v1/blocks/{number}`, and `POST /v1/reports` use a per-user Bearer token. Numbers require explicit E.164 form, such as `+13125550123`; the app does not guess a country. No transcript or audio is sent to the blocking service.

Provisioned local research builds can set `CALLSHIELD_SAFETY_BASE_URL` and `CALLSHIELD_SAFETY_TOKEN` in the untracked local build configuration. The URL must use HTTPS; the example shows xcconfig slash escaping. Server identity must match the user identity used for incoming calls. Never put an administrator token in a client. These build-provisioned test credentials are not a production sign-in or credential-enrollment system; production distribution still needs per-user secure provisioning and rotation.

An individual report is pending review. Only an administrator can activate a shared block. Caller ID spoofing and incorrect reports make automatic global blocking from one report inappropriate. Shared blocks cannot be removed with a user's personal-unblock action.

## Design basis

The Apple Design skill was applied to these native flows. The existing app serves older adults and family members; the design job is to keep help and personal choices visible without implying that an automated assessment verifies a caller.

- `accessibility.md > Mobility`: “Offer sufficiently sized controls.” Guardian, block, and sharing actions have at least 44-point hit regions and text labels.
- `privacy.md > Best practices`: “Be transparent about how your app collects and uses people’s data.” The message preview, optional excerpt toggle, server-sync status, and privacy copy disclose what is shared and when.
- `privacy.md > Best practices`: “Process data on the device where possible.” Message drafts are composed locally and contain an extractive excerpt only; no separate summarization service receives the text.
- `entering-data.md`, `sheets.md`, `typography.md`, `layout.md`, `color.md`, `designing-for-ios.md`, `buttons.md`, and `lists-and-tables.md` informed native Form/List layouts, standard sheets and dismissal, semantic colors, scalable text, and standard entry controls. The UI redesign agent owns the broader visual system and its contrast measurements.

## Verification

Initial focused simulator run: **32 passed, 0 failed, 0 skipped**, iPhone 17 Pro, iOS 26.5. Evidence: `native-test-summary.json` and `native-tests.log` in this folder. The run includes eight new behavior tests for guardian validation/deduplication/persistence, explicit manual blocking, offline report retry, failed unblock handling, report-only behavior, excerpt opt-in/no-fabrication, blocked incoming rejection, and refusal to block during an active call.

Final integration review: **42 passed, 0 failed, 0 skipped**, including the production behavior and transcript integration suites. Evidence: `native-final-review-summary.json` and `native-final-review-tests.log`. Four added regression tests cover an offline report not claiming a block, an unblock attempting to race an in-flight server block, insufficient transcript evidence carrying no score, and international numbers remaining distinct from similar US local numbers. Safety mutations and sync are serialized so that asynchronous requests cannot erase or resurrect a concurrent manual choice. Explicit international numbers compare exactly; only US incoming local forms use the existing US local-number convention.

The final international-number regression was rerun after tightening the last country-code guard: **1 passed, 0 failed** (`native-international-final-summary.json`, `native-international-final-tests.log`).

The Xcode build includes the native call UI and the new guardian sheets. The UI redesign agent separately verifies navigation, guardian setup, and the in-call flows. No real recipient was messaged and no real phone call was placed by these tests.

## Limits

- The guardian draft is an extractive check-in message, not an AI-generated summary. The current call contract provides only a real saved excerpt when caller-transcript sharing/retention has been explicitly enabled on the service. When none is available, the app says so.
- Guardian alerts are user initiated through Messages/sharing. There is no automatic push/SMS delivery or guardian-account linking, and message delivery/read receipts are not verified.
- Blocking applies to callma.-handled calls. It does not install a system-wide Phone-app blocking extension. The actual LiveKit incoming-event path is filtered before app ringing; its backend also enforces synced personal and reviewed shared blocks.
- The safety service is unconfigured until a tester is provisioned. Local blocks still work, and the interface labels server sync as pending rather than claiming global enforcement.
- Voice and transcript scores remain experimental. Neither the 0.75 guidance threshold nor any other score establishes caller identity or safety.
