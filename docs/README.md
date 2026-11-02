# docs — reading order

> **Review status:** ⏳ Unreviewed *(default; update when Yi reviews)*
>
> ✍️ Claude-authored (2026-09-20).

Formal reference notes for the IEEE paper collection. Read in order; each
builds on the previous one. Ad-hoc, dated findings live in `../scratch/`
instead.

| # | Doc | What it covers |
|---|-----|----------------|
| 01 | [01-architecture.md](01-architecture.md) | The five-stage pipeline, module responsibilities, data model, where to change what. |
| 02 | [02-data-sources.md](02-data-sources.md) | The 11 sources, the three discovery modes, per-source quirks, current dataset size. |
| 03 | [03-parsing-rules.md](03-parsing-rules.md) | Session detection, front-matter filtering, paper numbering, and the limits of each. |
| 04 | [04-viewer-and-marks.md](04-viewer-and-marks.md) | The static viewer, responsive layout, affiliation tooltips, and the like/mark/note system. |
| 05 | [05-operations.md](05-operations.md) | Updating the database, the one-click script, iCloud sync, troubleshooting. |
| 06 | [06-session-recovery.md](06-session-recovery.md) | Recovering sessions from the printed programme, the matching strategies and their guards, and the override table for years no rule can reach. |
| 07 | [07-history.md](07-history.md) | The full story behind each pitfall in `AGENTS.md`, and the handoff log up to 2026-10-22 (moved from `AGENTS.md`). |

Related, outside this folder:

- [`../AGENTS.md`](../AGENTS.md) — rules, current state, one-line pitfalls. **Read first.**
- [`../CODEMAP.md`](../CODEMAP.md) — which doc to update when a given code file changes.
- [`../ONGOING.md`](../ONGOING.md) — what is currently in flight.
- [`../DONE.md`](../DONE.md) — closed threads.
- [`../DEV_LOG.md`](../DEV_LOG.md) — the earlier maintenance log kept for history.
