# callma. implementation

Display name: **callma.**
Tagline: **call with more peace of mind.**

Both are lowercase and end in a period. The installed app name, permission descriptions, settings, calling UI, prototype metadata, and video materials use this spelling. Existing Xcode scheme, module, bundle identifiers, storage paths, and backend message keys retain their legacy names for compatibility.

All logo slots and exported app icons are temporary placeholders. `ios/scripts/draw_icon.swift` generates the placeholder exports; replace those exports and the shared `BrandMark` view when final artwork arrives.

The palette uses blue for primary actions, teal for answering/calling, coral for ending calls, and warm yellow for caution. Native surfaces and primary/secondary text adapt to the system appearance. Color never replaces a written result.

## Demo behavior

The SwiftUI demo now exposes the same five primary sections as production: Favorites, Recents, Contacts, Keypad, and Settings. The keypad accepts numbers and supports deletion and an international prefix. Call buttons show a demo-only explanation and never use telephony, open a dial URL, or create fake connected-call history. Favorites can be added and removed for the current session.

Voice explanations are removed from Settings and are available beside results on call and call-details screens. Native help uses a popover that adapts to a sheet in compact layouts. Help does not replace the visible warning or call controls.

The native staged call screen shows voice and scam-language feedback separately. Its risk values are explicitly authored sample data, not live inference; they appear only after the simulated analysis delay and are saved only if observed. Ending before analysis or declining a call does not invent a risk result.

The browser prototype received corresponding navigation and help updates earlier in this session. Final visual review is focused on the SwiftUI simulator at the user's request. The older Expo interface remains a separate sample-data concept, with updated branding and placeholder assets; its architecture is not the production phone app.

## Meeting materials

The three longer call scripts, two feature proposals, call flow, and video plan remain in this folder. The confirmed name replaces the earlier name vote. The trusted-contact shortcut, signal-based advice, and guardian companion remain proposals, not shipped capabilities.

## Verification

Final native results and screenshots are recorded in `DESIGN-REVIEW.md` and `branding-validation.json`. This is simulator evidence. Live routing, model accuracy, physical accessibility use, and deployment require separate checks described in `STATUS.md`.
