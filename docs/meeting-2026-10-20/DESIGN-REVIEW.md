# callma. native design review

## Summary

Applied the [Apple design skill](https://github.com/dickwu/apple-design-skill/blob/main/SKILL.md), including its accessibility, typography, color, layout, settings, buttons, tab-bar and popover guidance. Final visual review uses the actual SwiftUI app in Xcode's iOS Simulator, as requested. Browser screenshots are earlier supporting work and are not the final native design evidence.

The exact name **callma.** and tagline **call with more peace of mind.** are preserved. App icons and logo slots are explicitly temporary placeholders. Blue actions, teal call controls, coral end-call controls, and yellow caution surfaces provide the requested vibrant palette.

## Critical issues addressed

- **Missing demo dialer:** added Keypad and Favorites so both native modes have the same five primary sections. The demo accepts digits, deletion and an international prefix; Call explains that the demo cannot place calls. Contact Call buttons are blocked too. Automated tests verify that these actions do not create connected calls or history.
- **Redundant explanations:** removed the Settings glossary and added 44-point contextual information buttons beside voice results. Native popovers adapt to sheets on compact layouts. Visible safety guidance and call controls remain on the call screen.
- **Text contrast:** darkened secondary text and voice badges. Calculated sRGB contrast ratios are 5.76:1 for blue/white, 5.45:1 for secondary text/canvas, 6.33:1 for AI badges, 6.47:1 for human badges, 5.60:1 for unknown badges, and 5.88:1 for analyzing badges. White/teal Call is 4.58:1. These are individual token-pair checks, not a complete accessibility certification.

Guidance: `accessibility.md` → Vision ("44x44pt" touch targets and "4.5:1" contrast); `settings.md` → Best practices (minimize settings); `popovers.md` → Mobile (compact adaptation).

## Improvements and craft

- Scaled native fonts respect Dynamic Type, with a minimum configured size of 11 points. Retained semantic text styles. Larger-text Recents was inspected in the simulator; long contact names intentionally truncate, with full names available in details.
- Shared palette surfaces/text adapt to system appearance. Results include written labels and symbols, so color is not the sole signal.
- Native keypad digits, call controls, headings, cards and tab labels were inspected for alignment. The default iPhone layout fits the call controls without scrolling. Overflow remains available when text or screen constraints require it.
- Voice and scam-language feedback are separate cards. Authored demo risk appears only after the staged analysis delay and is saved only when observed. Early hang-up and declined calls do not invent a risk value.
- Reduce Motion avoids decorative animation. Button actions and information controls have accessibility labels.

Guidance: `typography.md` → Supporting Dynamic Type; `layout.md` → Visual hierarchy and Adaptability; `color.md` → Inclusive color; `buttons.md` → Best practices; `tab-bars.md` → clear labels and stable navigation.

## What works and evidence

**63 native unit/UI tests passed, zero failed**, on iPhone 17 Pro, iOS Simulator 26.5. Coverage includes five-tab navigation, dialing restrictions, favorites, contextual help, analysis timing, observed sample risk, production assessment states and call controls. See [test summary](branding-ios-test-summary.json) and [validation record](branding-validation.json).

Screenshots below were exported directly from the final Xcode test result; the blocked-call alert was additionally captured with simctl after a manual simulator check:

- [Native demo keypad](native-demo-keypad.png)
- [Native demo blocked-call alert](native-demo-call-blocked.png)
- [Native demo settings](native-demo-settings.png)
- [Native production settings](native-settings.png)
- [Native staged demo call](native-demo-call.png)
- [Native production call with injected test results](native-call-test-fixture.png)
- [Native larger-text Recents](native-larger-text.png)

## Platform notes and remaining checks

This review establishes simulator behavior and selected layouts. The production call screenshot uses injected test results; the demo uses sample callers. Neither establishes real model accuracy or working live telephony. Existing false-positive, outbound routing, consent, deployment and video tasks remain in [STATUS.md](STATUS.md).

The current custom tab bars remain; a future system TabView migration would improve automatic iPad adaptation. Largest accessibility sizes, a physical-device VoiceOver walkthrough, sunlight readability, and exhaustive dark-appearance states have not been validated. The larger-text screenshot documents the specific size reviewed rather than claiming all accessibility settings pass.
