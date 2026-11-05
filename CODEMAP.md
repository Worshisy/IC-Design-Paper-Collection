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
| `config.py` | `docs/02-data-sources.md`, `docs/01-architecture.md`, `AGENTS.md` §2 (pacing) | A source is added/removed, a discovery mode or `year_to_pubs` mapping changes, a rate limit or retry setting changes. |
| `scraper.py` | `docs/01-architecture.md`, `docs/02-data-sources.md`, `docs/05-operations.md` | API payload/endpoint changes, Early Access handling changes, affiliation enrichment changes, retry/resilience behaviour changes. |
| `parser.py` | `docs/03-parsing-rules.md` | **Any** change to `SKIP_*`, `FRONT_MATTER_ABSTRACTS`, the session regexes, ordering heuristics, numbering or de-duplication. Always run `tools/audit_front_matter.py` first, and add a unit case for whatever prompted the change. |
| `tools/restore_abstracts.py` | `docs/05-operations.md`, `AGENTS.md` §2 (pacing) and pitfalls 34, 36 | the endpoint, pacing, cache file or truncation test changes |
| `tools/repair_abstract_markup.py` | `docs/05-operations.md`, `AGENTS.md` pitfall 35 | which files it rewrites, or the markup test it uses |
| `textclean.py` | `docs/03-parsing-rules.md`, `docs/01-architecture.md`, `AGENTS.md` pitfall 35 | An entity mapping changes, or a new legacy markup form is handled. Re-run `tools/audit_front_matter.py` and `--reparse`. |
| `toc_sessions.py` | `docs/06-session-recovery.md`, `docs/03-parsing-rules.md` | **Any** change to a programme layout regex, a matching strategy, the candidate ranking, `is_plausible_session_name`, or the never-worse / degenerate-grouping guards. Re-run `tools/audit_session_contents.py` and a full sweep with before/after counts — this file is where regressions hide. |
| `session_overrides.py` | `docs/06-session-recovery.md` | The TSV format, the `__DROP__` marker, or the merge key changes. |
| `data/session_overrides.tsv` | `docs/06-session-recovery.md` | Any entry added or removed. **Always run `tools/audit_session_overrides.py` afterwards.** |
| `data/programmes.tsv` | `docs/06-session-recovery.md`, `docs/02-data-sources.md` | A programme URL added or removed. Re-run `--toc-sessions` for that year and confirm it was applied, not just fetched. |
| `esserc_tracks.py` | `docs/02-data-sources.md`, `docs/06-session-recovery.md` | A session or paper moves between the circuits and devices tracks. Run `tools/audit_device_tracks.py`. |
| `vlsi_tracks.py`, `data/vlsi_technology_papers.txt` | `docs/02-data-sources.md` | A paper moves between the Circuits and Technology tracks. Run `tools/audit_device_tracks.py`. |
| `models.py` | `docs/01-architecture.md` (data model table) | A field is added, removed or changes meaning. |
| `validation.py` | `docs/01-architecture.md`, `docs/05-operations.md` | A validation rule or an exported column changes. |
| `html_builder.py` | `docs/04-viewer-and-marks.md`, `docs/01-architecture.md` | Row/search payload fields change, page ordering changes, the annotations seed changes. |
| `templates/_styles.css.j2` | `docs/04-viewer-and-marks.md` (layout table) | Breakpoints or the density/clamp behaviour change. |
| `templates/_scripts.js.j2` | `docs/04-viewer-and-marks.md` | Mark/like/note behaviour, storage keys, or the save path change. |
| `templates/year.html.j2`, `templates/index.html.j2` | `docs/04-viewer-and-marks.md` | Columns, controls or filters change. |
| `tools/refresh_citations.py` | `docs/05-operations.md`, `docs/04-viewer-and-marks.md` | Which fields it copies, where the fetch date is stored, or how a year is skipped. |
| `update_database.py` | `docs/05-operations.md` | Step order, default year window, CLI flags or the iCloud sync rules change. |
| `update.bat` | `docs/05-operations.md`, `README.md` | Flags or the interpreter selection change. |
| `serve.py` | `docs/04-viewer-and-marks.md`, `docs/05-operations.md` | The save endpoint or the default port changes. |
| `utils.py` | `docs/01-architecture.md`, `docs/05-operations.md`, `AGENTS.md` §2 | HTTP session, retry wrapping, the rate limiter's gap, seed or long-run rest, or JSON IO changes. |
| `templates/surveys_index.html.j2`, `html_builder.build_surveys_index` | `docs/04-viewer-and-marks.md` (and the private `surveys/README.md`) | the card fields or the copy into `site/surveys/` change |
| `.gitignore` | `README.md`, `AGENTS.md` | What is or is not tracked changes. |

## Always-in-scope indexes

- `README.md` — the workspace map and quick start.
- `AGENTS.md` — rules, current state, one-line pitfalls (stories in `docs/07-history.md`).
- `ONGOING.md` / `DONE.md` — open threads / closed-thread index.
- `docs/README.md` — the reading order, if a doc is added or renumbered.

## Dataset numbers

Any figure quoted in `docs/02-data-sources.md` must come from a
`validation_summary.csv` produced by a run you actually did. When the dataset
is rebuilt, re-read those files and update the table — do not carry old
numbers forward.
