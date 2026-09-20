# scratch — ad-hoc findings

> ✍️ Claude-authored (2026-09-20).

Short, dated, informal notes. One finding per file. No review badges here —
these are working notes by nature. Anything that grows past a page, or that
gets cited repeatedly, should be promoted to a numbered doc in `../docs/`.

Conventions:

- `YYYY-MM-DD-<slug>.md` — a dated finding.
- `_<slug>.md` — transient (session-resume markers, agent-output buffers);
  the leading underscore means "delete me when done".
- Once 3+ notes share a topic, cluster them into `scratch/<topic>/` with a
  TOC `README.md` and list the folder here.

## Notes

| Note | What it records |
|---|---|
| [2026-09-20-front-matter-audit.md](2026-09-20-front-matter-audit.md) | The regression sweep behind the front-matter filter: measured counts, false positives found and fixed, and the rerunnable test. |
| [2026-09-20-style-review.md](2026-09-20-style-review.md) | The Sonnet style/quality review of the original code, with what was acted on and what was deliberately left. |
| [2026-09-20-api-behaviour.md](2026-09-20-api-behaviour.md) | What the IEEE endpoints actually return: affiliations, content types, throttling, encoding. |
| [2026-09-20-source-audits.md](2026-09-20-source-audits.md) | Per-source title audits: what was fixed, what was measured and rejected, and the false positive the regression tool caught. |
