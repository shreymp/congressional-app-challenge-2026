# Callma UI/UX revamp (branch `improved-ui`)

Source: the "Paper & Midnight" design specification (warm Paper Tan, Space Black,
Midnight Blue, Burnished Copper). Audience: older adults, so every decision below
favours legibility, large targets and plain language over density.

## Goals

1. Calm during ordinary use, unmistakable when something important happens.
2. Nothing a caller-safety decision depends on is communicated by color alone.
3. Readable without the Larger text toggle; still works at the largest Dynamic Type sizes.

## What changes

| Area | Before | After |
| --- | --- | --- |
| Colors | Hex values scattered through every view; green brand | Semantic tokens in `Theme` (DesignSystem.swift) with light and dark values from the spec |
| Appearance | Forced light; forced dark on calls | Follows the system, with a System / Light / Dark choice in Settings |
| Text | 9–12 pt captions, tiny uppercase labels | Dynamic Type text styles only; nothing below `.subheadline` (15 pt); no tracked uppercase |
| Tab bar | 9 pt labels, color-only selection | 13 pt semibold labels, selected tab gets a filled pill plus color |
| Lists | Hairline rows on white | Warm White grouped cards, 52 pt avatars, whole row tappable, chevron |
| Filters / search | iOS segmented control, 37 pt field | 52 pt high-contrast filter buttons and search field with a visible border |
| Voice labels | Small pill, color plus icon | Status badge with a distinct icon per state (person, warning, question mark, waveform) and semantic color pairs |
| Active call | Dark green gradient, small analysis text | Theme background, one central voice-check card with a 22 pt verdict; Likely AI adds a muted-red "What to do" panel |
| Call controls | 59–70 pt circles, 12 pt labels, scroll with content | 76–84 pt controls with readable labels, pinned to the bottom so they never scroll away; End call is a full-width red button |
| Keypad | 74 pt keys, 9 pt letters | 80 pt keys with outlined surfaces, larger letters |
| Detail sheets | Loose stacked text | Status card, information card, plain-language note; Recents entries can be removed with a visible button, not only a swipe |
| Settings | Mixed rows | Grouped sections: Display, Calling, Understanding voice labels, Privacy |

## Status semantics

| Voice | Icon | Light fg / bg | Dark fg / bg |
| --- | --- | --- | --- |
| Likely human | `person.fill` | #207057 / #E6F3EC | #9AD9C0 / #24443B |
| Likely AI | `exclamationmark.triangle.fill` | #A93A44 / #FBEAEC | #FF9BA5 / #4A2B30 |
| Analyzing | `waveform` | #315F93 / #E7ECF1 | #A5C8F5 / #253B55 |
| Unknown (inconclusive) | `questionmark.circle.fill` | #94601E / #FAF1E0 | #F1C98B / #473A29 |

End call uses Deep Red #B43D46 and only appears on call controls, never as a status.
Missed calls show "Missed call" in words; they never get a voice badge because they are never analysed.

## Rules for future screens

- Use `Theme.*` colors, `PrimaryButtonStyle` / `SecondaryButtonStyle`, `.card()` and `SectionHeader`; never a raw hex.
- Fonts: `.largeTitle` screen titles, `.title2`/`.title3` section headings, `.body` content, `.callout` secondary, `.subheadline` metadata.
- Touch targets: 52 pt minimum for anything tapped often, 76 pt+ for call controls.
- Copper is the brand detail only (shield mark). It is never a button or status color.
- No pulsing or constant animation to signal analysis.
- Voice wording must not imply the caller is verified or safe.

## Out of scope for this branch

- Renaming the product to "Callma." (the spec's working name). The app, tests and alerts still say Callma.
- The `frontendscreens` web prototype and the Expo `frontend` app.
- New app icon artwork.
