# Browser call-screen verification — 2026-10-21

Verified the local React/Vite **simulated browser prototype** in the in-app browser at 320×568 and 390×844 CSS pixels. No real phone call, audio, transcript, model inference, notification, or external message was involved. These results do not validate scam-detection accuracy or native iOS behavior.

## Result

Both incoming and connected calls fit the requested viewports with no main call or document overflow. Voice and Words open one anchored nonmodal detail region without moving the caller identity, controls, or hang-up. The region remains above controls. At the compact size the detail text scrolls internally; the document stays at scroll position 0,0.

| Check | 320×568 | 390×844 |
| --- | --- | --- |
| Document scroll size equals viewport | 320×568 | 390×844 |
| Call screen client/scroll height | 507 / 507 | 783 / 783 |
| Caller/hang-up positions stable opening details | Passed | Passed |
| Open details stay above controls | 10px gap | At least 14px gap |
| Internal details scrolling | 67px viewport; 335px content; scrollTop advanced to 267.5 | Voice fits; Words bounded at 155px |
| Incoming Accept/Decline remain visible | Passed | Passed |

The End and Decline controls also use a plain rotated handset, preserving their accessible labels and button geometry. Final screenshots were refreshed and lint/build rerun after this icon correction.

One defect found and fixed during verification: compact detail text initially had only a 14px viewport. The compact-height CSS now uses tighter identity spacing, 48px chips, and 56px circular controls, yielding 67px of scrollable text while preserving the caller identity and control region. All interactive targets remain at least 44px.

## Interaction checks

- Accept changes incoming to connected and begins the existing simulated assessment/timer.
- Human example produces “Likely human” separately from Words “8 / 100”; AI example produces “Likely AI” separately from Words “94 / 100 · High”. The disclaimer explains these are simulated scores rather than scam probabilities, and a human voice/low score does not verify safety.
- Voice → Words switches directly with exactly one detail region.
- Escape closes the region and returns keyboard focus to its chip.
- Close returns focus to the chip that opened it.
- Tapping mute outside an open Words region both closes the region and changes mute state; the next label becomes Unmute with aria-pressed=true.
- Speaker toggles aria-pressed=true. Keypad stays disabled and is labeled unavailable in demo.
- End adds a received Recents item with the simulated voice result; Decline adds a missed item with Unknown voice.
- The app's own “Larger text” switch was checked at 320×568: larger detail text remains bounded and controls stay visible. This is **local CSS/font enlargement, not OS Dynamic Type**, browser zoom, or a screen-reader certification.
- Browser warning/error capture was empty.

## Checks and limits

`npm run lint`, `npm run build`, and scoped `git diff --check` all passed after the compact fix. Reduced-motion and reduced-transparency CSS from the existing prototype remains in place; OS preference toggling was not exercised in this browser session. Landscape, browser zoom, maximum OS text size, other engines, and native device behavior were not part of these two-viewport checks.

Apple-design guidance used: `layout.md` → Visual hierarchy (“Use progressive disclosure to make layouts cleaner and easier to interact with”); `popovers.md` → Best practices (“Ideally, a popover doesn’t cover ... any essential content”); `accessibility.md` → Mobility (44×44pt default controls). These principles were translated into DOM buttons, CSS sizing, keyboard focus, and a bounded region for this browser prototype. The call screen's single dark appearance follows the requested phone-call visual direction; this is not a claim of a native system Phone component.

## Evidence

- `incoming-320x568.jpg`, `incoming-390x844.jpg`: incoming call.
- `connected-320x568.jpg`: compact controls and independent chips.
- `words-320x568.jpg`: compact open warning detail, with hang-up visible.
- `voice-390x844.jpg`, `words-390x844.jpg`: normal-size independent assessments.
- `large-text-320x568.jpg`: local Larger text switch on, warning detail open.
- `measurements.json`: DOM-backed geometry and internal scroll readings.
- `browser-warnings-errors.json`: captured warnings/errors (empty array).

The temporary viewport override was reset and the agent-created browser tab was closed. The owned Vite preview (`npm run dev`, exec sessions 45330 and final icon capture 51900, http://127.0.0.1:3000/) was stopped after evidence was saved. No other processes were stopped.
