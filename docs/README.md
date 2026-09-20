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
| 02 | [02-data-sources.md](02-data-sources.md) | The 9 sources, the three discovery modes, per-source quirks, current dataset size. |
| 03 | [03-parsing-rules.md](03-parsing-rules.md) | Session detection, front-matter filtering, paper numbering, and the limits of each. |
| 04 | [04-viewer-and-marks.md](04-viewer-and-marks.md) | The static viewer, responsive layout, affiliation tooltips, and the like/mark/note system. |
| 05 | [05-operations.md](05-operations.md) | Updating the database, the one-click script, iCloud sync, troubleshooting. |

Related, outside this folder:

- [`../AGENTS.md`](../AGENTS.md) — canonical workspace state, hard rules, gotchas, handoff log. **Read first.**
- [`../CODEMAP.md`](../CODEMAP.md) — which doc to update when a given code file changes.
- [`../ONGOING.md`](../ONGOING.md) — what is currently in flight.
- [`../DEV_LOG.md`](../DEV_LOG.md) — the earlier maintenance log kept for history.
