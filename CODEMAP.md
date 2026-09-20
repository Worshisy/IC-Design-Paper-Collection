# CODEMAP — code file → the docs that describe it

> **Review status:** ⏳ Unreviewed *(default; update when Yi reviews)*
>
> ✍️ Claude-authored (2026-09-20).

Read the relevant row **before** a substantial change; update every doc it
names **after**, and re-check this table at commit time — the commit is the
gate. `README.md`, `AGENTS.md` and `docs/README.md` are always in scope when
structure changes.

| Code file | Documented in | Update the doc when… |
|---|---|---|
| `config.py` | `docs/02-data-sources.md`, `docs/01-architecture.md` | A source is added/removed, a discovery mode or `year_to_pubs` mapping changes, a rate limit or retry setting changes. |
| `scraper.py` | `docs/01-architecture.md`, `docs/02-data-sources.md`, `docs/05-operations.md` | API payload/endpoint changes, Early Access handling changes, affiliation enrichment changes, retry/resilience behaviour changes. |
| `parser.py` | `docs/03-parsing-rules.md` | **Any** change to `SKIP_*`, `FRONT_MATTER_ABSTRACTS`, the session regexes, ordering heuristics, numbering or de-duplication. Always run `tools/audit_front_matter.py` first, and add a unit case for whatever prompted the change. |
| `textclean.py` | `docs/03-parsing-rules.md`, `docs/01-architecture.md` | An entity mapping changes, or a new legacy markup form is handled. Re-run `tools/audit_front_matter.py` and `--reparse`. |
| `models.py` | `docs/01-architecture.md` (data model table) | A field is added, removed or changes meaning. |
| `validation.py` | `docs/01-architecture.md`, `docs/05-operations.md` | A validation rule or an exported column changes. |
| `html_builder.py` | `docs/04-viewer-and-marks.md`, `docs/01-architecture.md` | Row/search payload fields change, page ordering changes, the annotations seed changes. |
| `templates/_styles.css.j2` | `docs/04-viewer-and-marks.md` (layout table) | Breakpoints or the density/clamp behaviour change. |
| `templates/_scripts.js.j2` | `docs/04-viewer-and-marks.md` | Mark/like/note behaviour, storage keys, or the save path change. |
| `templates/year.html.j2`, `templates/index.html.j2` | `docs/04-viewer-and-marks.md` | Columns, controls or filters change. |
| `update_database.py` | `docs/05-operations.md` | Step order, default year window, CLI flags or the iCloud sync rules change. |
| `update.bat` | `docs/05-operations.md`, `README.md` | Flags or the interpreter selection change. |
| `serve.py` | `docs/04-viewer-and-marks.md`, `docs/05-operations.md` | The save endpoint or the default port changes. |
| `utils.py` | `docs/01-architecture.md` | HTTP session, retry wrapping or JSON IO changes. |
| `.gitignore` | `README.md`, `AGENTS.md` | What is or is not tracked changes. |

## Always-in-scope indexes

- `README.md` — the file list and quick start.
- `AGENTS.md` — workspace map, hard rules, gotchas, handoff log.
- `docs/README.md` — the reading order, if a doc is added or renumbered.

## Dataset numbers

Any figure quoted in `docs/02-data-sources.md` must come from a
`validation_summary.csv` produced by a run you actually did. When the dataset
is rebuilt, re-read those files and update the table — do not carry old
numbers forward.
