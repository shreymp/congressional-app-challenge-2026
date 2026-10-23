# callma. native UI redesign

Historical redesign report. Keshav rejected this appearance on October 21 and requested restoration of the previous design. See `../STATUS-2026-10-21.md` for current state; these screenshots and geometry checks are retained as historical evidence.

## Design review: production SwiftUI calling app

### Summary
The app helps people place and review calls while keeping voice estimates separate from scam-language estimates. Initial rating: Needs work. The final design thesis is a familiar phone interface: caller above circular call controls and a red hang-up button. Two compact, independent checks open anchored explanations without moving the call screen. The latest user direction explicitly requires no main call-screen scrolling and strong Apple Phone / Google Phone inspiration.

### Critical findings addressed
- Larger text could lower an accessibility-size system preference to xxLarge. Preserve the larger of the two values. `accessibility.md › Vision`: “Support larger text sizes.”
- Small search-clear and favorite actions lacked a 44 pt hit region. Add padding and minimum targets. `buttons.md › Best practices`: “a hit region of at least 44x44 pt”.

### Improvements
- High: custom HStack tabs and hand-built headings bypass native bar adaptation. Replace with TabView and NavigationStack. `tab-bars.md › Best practices`: “Include tab labels to help with navigation.”
- High: forced light ordinary sheets ignored system appearance. Use adaptive colors for browsing, contacts, settings, and sheets. The active call intentionally uses a dark neutral Phone-style presentation, matching the later user direction; this is product-specific design judgment. `dark-mode.md › Best practices`: “Ensure that your app looks good in both appearance modes.”
- Medium: repeated gradients, placeholder logo artwork, and tiny captions competed with call information. Remove them; preserve the callma. wordmark in Settings. `layout.md › Visual hierarchy`: “Order content by relative importance.”
- High: a long scrolling call screen put analysis ahead of calling. Replace it with fixed caller identity, two compact Voice/Words buttons, standard circular Mute/Keypad/Speaker controls, and a red circular End Call. Keypad remains disabled when the backend cannot send digits. Explanations appear in anchored overlays; only the bounded explanation itself may scroll at large text sizes. This layout choice follows the user’s explicit constraint and is design judgment.

### Compact token plan
Color uses six core roles: canvas (#F5F7FA / #0D1726), surface (#FFFFFF / #182638), primary content (#17243A / #EEF4FF), secondary content (#53657D / #B5C5DD), interactive accent (#195ED9 / #8EB8FF), and warning (#78510E on #FFF3DA / #FFD78E on #392E19). High-contrast variants further strengthen accent, text, and separators. Familiar red and green are reserved for ending and answering calls.

| Role | Foreground | Surface | WCAG contrast |
| --- | --- | --- | --- |
| primary/light | #17243A | #FFFFFF | 15.56:1 |
| primary/dark | #EEF4FF | #182638 | 13.85:1 |
| secondary/light | #53657D | #FFFFFF | 5.96:1 |
| secondary/dark | #B5C5DD | #182638 | 8.74:1 |
| accent/light | #195ED9 | #FFFFFF | 5.76:1 |
| accent/dark | #8EB8FF | #182638 | 7.61:1 |
| warning/light | #78510E | #FFF3DA | 6.40:1 |
| warning/dark | #FFD78E | #392E19 | 9.73:1 |

Typography uses system large titles for destinations, title2 for caller identity, headline for assessment labels, body for explanations, and caption only for supporting metadata. Numbers use monospaced digits. Semantic styles support Dynamic Type and Bold Text.

Layout: system bars frame the browsing destinations. During a call, a fixed single column places caller identity above compact checks, optional safety guidance, and familiar call controls. Anchored explanation overlays preserve the caller and hang-up coordinates.

```
Compact                         Regular
[<system navigation title>]     [<system navigation title>]
[search / grouped content]      [   readable content column   ]
[                       ]       [   grouped details           ]
[system tab bar         ]       [system-adaptive navigation   ]

Call
[caller / number / duration]
[ Voice v ]     [ Words v ]    <- tap for anchored explanation
[ compact safety / guardian ]
[ mute ] [ keypad ] [speaker]   <- circular, capability-aware
[       red hang-up         ]  <- fixed, no main scrolling
```

Signature: paired, plainly named voice and language checks; no combined safety score. Motion is limited to existing brief press feedback and call transitions, disabled with Reduce Motion. A restrained dark neutral gradient (#2B3545 to #111721) and translucent circular controls recall the Phone call context; overlays use opaque surfaces. callma. branding remains text plus unfinished app-icon assets.

### Plan critique
A generic dashboard would emphasize a combined score. Here the defining structure reflects the actual two independent checks and a phone task. Removed the logo tile and expanded dashboard-like assessment cards from the call. Native controls carry navigation; the app identity stays in wording, the reserved blue accent, and the independent checks. A dark call-context background is retained specifically to match the user’s Phone direction.

### What works
Keep contact initials, the clear distinction between voice and words, permission-in-context contacts access, caller-only transcript messaging, unavailable states, and capability-based call controls.

### Verification
Final visual/interaction review: **Good**. The Phone hierarchy is recognizable and the two checks remain independently legible. Removed the expanded call-screen dashboard; there is no additional decorative element to remove. Source syntax and scoped whitespace checks pass.

Simulator evidence: iPhone 17 Pro / iOS 26.5, Xcode 26.6. The final production + selected demo suite passed **11 tests, 0 failures** (`/tmp/callshield-ui-phone-final.xcresult`, `ui-tests.log`). It covers native destination navigation, keypad/error behavior, fixed call layout, caller and hang-up coordinate equality before/after opening an anchored explanation, Close and outside-tap dismissal, independent voice/transcript .75 boundaries, .74 below-threshold behavior, guardian preview/setup with no send, one return reminder, and largest system text. Final wrapping/accessibility adjustments and the bounded popover passed the two-test rerun in `accessibility-final.log`. After the last lowercase branding updates, the five affected call/navigation/guardian/demo tests passed again with 0 failures (`/tmp/callma-ui-final.xcresult`, `final-callma.log`, `final-test-summary.json`). Those final-build screenshots replace earlier images in the screenshot folder. The popup is bounded above the measured call-control top edge, the hang-up center is outside its frame, and hang-up remains hittable while it is open.

Screenshots are in `screenshots/`; production call screenshots use the Debug fixture. No physical-device calling or model-accuracy claim is part of this UI verification. The simulator cannot validate actual SMS sending, real microphone/audio routing, incoming cellular calls, or real-world detection quality.

### Safety interactions and limits
- Either current experimental transcript score or voice AI score at or above 0.75 reveals concrete safety steps. The estimates remain separate; a human-sounding voice never clears a transcript warning.
- Alert Guardian opens recipient selection, an optional excerpt choice, and a message preview. Sending is a separate, explicit action in the system composer or sharing app. No automatic message is sent by crossing a threshold.
- If a call has a score of at least 0.9 when the app goes into the background, callma. offers one reminder when the user returns. iOS does not permit intercepting or cancelling the Home gesture, and this implementation does not claim to prevent leaving the app.
- Model scores are not calibrated probabilities of fraud. A low score does not establish identity or safety. Stale/unavailable evidence cannot create a new threshold warning.
- Local UI tests use an explicit Debug-only analysis fixture. Screenshots from that fixture are interface evidence, not successful live detection or a delivered guardian notification.


### Primary Phone references and design interpretation
- [Apple: While on a call on iPhone](https://support.apple.com/en-gb/guide/iphone/iph3c9951d7/ios): standard Mute, Keypad, audio-route, and end-call tasks. callma. follows the familiar caller/control hierarchy rather than adding unsupported call actions.
- [Google: Make and receive phone calls](https://support.google.com/phoneapp/answer/2811745?hl=en-nz): familiar mute, speaker/audio-route, and keypad behavior. callma. uses plainly named controls and short status text.
- The exact spacing, anchored overlay implementation, and dark neutral colors are design judgments informed by those task patterns; this is not an exact copy or an assertion of current pixel parity with either app.

### Call-context contrast
Computed from source hex values, using the lightest gradient stop as the conservative call background: primary text #EEF4FF on #2B3545 is 11.20:1; secondary #B5C5DD is 7.06:1; white on red #BF323A is 5.63:1. Prominent blue actions use explicit white in light mode (5.76:1) and #0D1726 in dark mode (8.95:1).

### Platform limits
The call layout keeps information and controls within a fixed screen. At accessibility text sizes, the avatar and duplicate number are omitted, while full caller identity remains available to accessibility; compact chip values and control captions can shrink to fit their physical control columns. The dial pad caps glyph scaling at xxxLarge to keep all twelve digit targets present; digit labels remain accessible. Full explanatory text respects larger system text and can scroll inside the bounded overlay. VoiceOver reading order, smallest older supported devices, landscape, real Bluetooth routing, physical call controls, and actual guardian delivery still need device testing.

### Files changed by the UI subagent
- `Production/ProductionCallView.swift`: fixed Phone-style active/incoming/connecting UI, bounded anchored explanations, manual guardian entry point, experimental safety guidance, one reminder after return.
- `Production/ProductionRootView.swift`: native tabs and navigation, Dynamic Type preservation, per-call presentation identity, empty state component.
- `Views/DesignSystem.swift`: semantic palette, high contrast, neutral human badge, callma. text brand, generic phone symbol while final artwork is unfinished, 44 pt help target.
- `Views/CallScreen.swift`: fixed Phone-style demo calls and anchored explanation, preserving simulated controls/labels.
- `Production/ProductionVoicemailView.swift`: system-appearance support and callma. copy.
- `App/Info.plist`: callma. display/permission wording only; safety configuration fields belong to the native feature agent.
- `Production/ProductionStore.swift`: Debug analysis-fixture score variations only; guardian/blocking behavior belongs to the native feature agent.
- `CallshieldUITests/ProductionUITests.swift` and `CallshieldUITests/CallshieldUITests.swift`: native navigation, fixed layout, anchored details, score boundaries, guardian review, accessibility, and updated brand assertions.
