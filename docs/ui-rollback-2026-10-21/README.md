# Previous design restoration — October 21, 2026

Keshav rejected the redesign and requested the previous appearance. Restore the accepted design from `43afa929`, which matches the five saved pre-redesign native source files in `/tmp/callshield-ui-before/`. This supersedes the dark fixed-call redesign documented in `docs/ui-redesign-2026-10-20/` and the earlier October 21 preview screenshots.

The rollback concerns visual layout, colors and navigation. Preserve lowercase **callma.**, guardian setup and reviewed sharing, manual blocks/reports, experimental safety thresholds, the return reminder, insufficient-evidence handling, and detector/backend work. No Git reset, checkout, commit, push, deployment or model change is part of the rollback.

## Browser and Expo

- `frontend/App.js` and `frontendscreens/phone.css` restored byte-for-byte from `43afa929`.
- `frontendscreens/CallScreen.tsx` restored from the same design with only the current 0.75 warning threshold and score-out-of-100 wording retained.
- Browser TypeScript check and Vite production build passed (1,668 modules).
- Restored Expo JSX parsed successfully using its installed Babel parser. No new Expo runtime/export claim is made for this rollback.
- Preview sources before this rollback are preserved in `/tmp/callma-design-rollback-20261021/before/`.

[Native verification](native.md) and [the restored call screenshot](native-call-restored.png) are saved alongside this report. The restored app built; 36 unit and 11 selected UI checks passed across the initial run and focused rerun. All 51 protected backend/native feature implementation hashes remained unchanged. Final repository whitespace checks passed. Historical redesign-specific geometry assertions do not describe the restored appearance.
