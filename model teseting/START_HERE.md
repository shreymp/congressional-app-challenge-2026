# Model testing

**Latest model comparison:** [Compare V2 and V3/README.md](Compare%20V2%20and%20V3/README.md) — October 23, 2026.

| Folder / file | Purpose |
|---|---|
| Compare V2 and V3/ | Self-contained V2/V3 checkpoint comparison: report, audio/model copies, scores and validation |
| benchmark/ | Earlier versioned pipeline/window-selection experiments and their runs |
| validation/ | Earlier data policy, calibration and release-gate work |
| results/, snapshots/, README.md, regression_report.md | Preserved original pipeline evaluation and source snapshots |
| audio/, weights/ | Shared inputs used by prior runs |
| logs/, provenance/, cache/ | Earlier execution logs, evidence and cached tools |

The new comparison is contained in its own folder, with inputs, source snapshots, results and logs separated. Earlier root-level files are preserved because the versioned benchmark verifies their locations and checksums. Use this index to navigate without mixing new results with the frozen historical evaluation.
