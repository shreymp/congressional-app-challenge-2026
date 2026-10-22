# Native design restoration

The user requested the previous design. The five backups in `/tmp/callshield-ui-before` exactly matched accepted commit `43afa929`; those originals were the source, rather than a new design. Current affected source was saved first in `before/`.

DesignSystem, ProductionRootView, ProductionVoicemailView and demo CallScreen are now byte-for-byte identical to `43afa929`. The other demo screen files already matched and were left alone. The prior blue palette/gradients, placeholder logos, custom bottom tabs, contact/search layout, Settings card and call-page styling are restored with lowercase `callma.`.

ProductionCallView retains the independent experimental voice/transcript `.75` safety triggers, the `.9` once-on-return reminder and guardian draft sheet. A small safety card uses the original call-card style. Both actual scores and insufficient-evidence behavior remain supported; no detector/model logic changed. The original call page can scroll when content does not fit, including large text.

ProductionPhoneScreens retains the manual post-call block/report choices, guardian add/remove flow, privacy copy and synchronization status. A guardian card sits above the original Contacts content; the original Settings page opens Blocked Numbers in a sheet. No model score automatically blocks a caller. No real calls or messages were sent.

All **51 protected feature files** match the root's pre-rollback hashes: `source-preservation.json`. Store/model/service/config/project files were not modified by this rollback.

## Validation

- Built and tested with the existing iPhone 17 Pro simulator, iOS 26.5, UUID `10469AE2-2454-4954-913E-A1100BE59050`.
- **36 ProductionTests passed**, covering guardians/draft excerpt consent, manual blocks/reports, offline synchronization, international matching, insufficient transcript evidence, incoming-call rejection, call/session persistence and rendering.
- **11 selected UI tests pass across the initial run and focused rerun**: original production/demo navigation, keypad simulator error, both pipeline scores, independent `.75` triggers / below-threshold case, once-only return reminder, largest-text call-control reachability, Contacts guardian setup, Settings blocked-number sheet and reviewed guardian preview/setup without sending.
- The initial run passed 45/47. One help selector expected `About Human` instead of the restored `About Likely human`; it was corrected. The return-reminder test's obsolete immediate End-control hittability assertion failed after reactivation; that redundant fixed-layout-era assertion was removed. The reminder assertions themselves passed; End reachability is exercised separately on the restored scrolling call page and at largest text size. Both affected tests passed their focused rerun (2/2). Logs and structured summaries are retained.
- `git diff --check -- ios` passed. No extra test expansion or app redesign followed the rollback.

Evidence: [restored call](native-call-restored.png), `tests.log`, `initial-test-summary.json`, `rerun.log`, `rerun-test-summary.json`, and exported attachments. Result bundles are `/tmp/callma-ui-rollback-20261021.xcresult` and `/tmp/callma-ui-rollback-rerun-20261021.xcresult`.

These checks are simulator/fixture evidence, not live-call, real-message delivery, classifier accuracy or physical-device validation. The prior fixed-layout/popover screenshots and tests are superseded by this user-requested restoration. No commit or push was made; both test processes completed.

Changed native source: `Views/DesignSystem.swift`, `Views/CallScreen.swift`, `Production/ProductionRootView.swift`, `Production/ProductionCallView.swift`, `Production/ProductionPhoneScreens.swift`, `Production/ProductionVoicemailView.swift`; adapted test files: `ProductionUITests.swift`, `CallshieldUITests.swift`.
