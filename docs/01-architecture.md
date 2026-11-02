# 01 — Architecture

> **Review status:** ⏳ Unreviewed *(default; update when Yi reviews)*
>
> ✍️ Claude-authored (2026-09-20).

## The pipeline

Five stages. Each writes to disk, so any stage can be re-run alone.

```
  1 DISCOVER      year -> IEEE publication number(s)          scraper.py
        |
  2 FETCH         POST /rest/search, paged                    scraper.py
        |         raw API records
  3 PARSE         records -> ConferenceYear/Session/Paper      parser.py
        |         front matter dropped, sessions assigned
        |-------> output/<id>/json/<year>.json
  4 VALIDATE      structural checks, CSV export                validation.py
        |-------> output/<id>/csv/*.csv, validation_summary.*
  5 BUILD         Jinja2 -> static HTML                        html_builder.py
                  site/<id>/year_<year>.html, index.html
                  site/index.html (conference picker)
```

Two optional passes hang off this spine:

- **Affiliation enrichment** (`scraper.enrich_affiliations`) runs between 3
  and 4. It is separate because it costs one HTTP request *per paper*.
- **iCloud sync** (`update_database.sync_to_icloud`) runs after 5, once, and
  copies only files whose content changed.

## Why the REST API and not HTML

IEEE Xplore pages are JavaScript-rendered single-page apps, so fetching the
HTML yields an empty shell. The scraper calls the same endpoint the Xplore
frontend calls:

```
POST https://ieeexplore.ieee.org/rest/search
{ "punumber": "<publication number>",   // which proceedings/journal
  "ranges": ["2025_2025_Year"],         // journals only
  "sortType": "vol-only-seq",           // proceedings order
  "rowsPerPage": 100, "pageNumber": 1 }
```

`sortType: vol-only-seq` matters: it returns records in printed order, which
is what lets session headers precede their papers.

A second endpoint supplies affiliations, which the search API omits entirely:

```
GET https://ieeexplore.ieee.org/rest/document/<articleNumber>/authors
-> { "authors": [ { "name": ..., "affiliation": [ ... ] } ] }
```

## Module responsibilities

| Module | Owns | Do not put here |
|---|---|---|
| `config.py` | Source definitions (`CONFERENCES`), `ScraperConfig`, all paths. **Source of truth for which sources exist.** | Parsing or HTTP logic. |
| `utils.py` | Shared HTTP session, retry wrappers (`retrying_post`, `retrying_get`), JSON IO, logging setup. | Anything source-specific. |
| `scraper.py` | Year discovery, paging, Early Access handling, affiliation enrichment. | Title interpretation. |
| `parser.py` | Turning raw records into the data model: front-matter rules, session detection, paper numbering, de-duplication. | Network calls. |
| `textclean.py` | Decoding HTML entities and converting pre-Unicode IEEE markup (`/spl mu/` → `µ`, `/sup 2/` → `²`). | Anything structural. |
| `models.py` | `Paper` / `Session` / `ConferenceYear` pydantic dataclasses. | Behaviour. |
| `validation.py` | Structural checks and CSV/combined exports. | Fixing data (it reports, it does not repair). |
| `html_builder.py` | Jinja environment, row flattening, the annotation seed file. | Presentation (that is in `templates/`). |
| `templates/` | All markup, CSS and browser JS. | Data decisions. |
| `update_database.py` | Orchestration + iCloud sync. | Anything the library modules should own. |
| `serve.py` | Local HTTP server that persists marks. | Dataset logic. |

## Data model

`ConferenceYear` -> `Session[]` -> `Paper[]` (`models.py`).

A `Paper` carries:

| Field | Meaning |
|---|---|
| `paper_number` / `inferred_paper_number` | Canonical `"<session>.<index>"`, always sequential within the session. |
| `displayed_paper_number` | The number printed in the title, when the title had one. May disagree with the canonical number; mismatches are logged. |
| `article_number` | IEEE article ID. **The stable identity** — used to key affiliations and Yi's marks. |
| `authors` | Author names, in order. |
| `affiliations` | Index-aligned with `authors`: `affiliations[i]` belongs to `authors[i]`. Empty until enrichment has run. |
| `author_affiliations_raw` | Deduplicated affiliations joined with `"; "`, for display and CSV. |
| `paper_url`, `doi` | Links. |
| `citation_count` | IEEE Xplore's "Cited by Papers" count when the record was fetched (`citationCount`). Refreshed by `tools/refresh_citations.py`; fetch dates in `output/citations_updated.json`. |

For journals, "session" means "issue" — the same structure is reused, with
`session_name` set to `"Vol. 61, Issue 3"` (or `"Vol. 9"` when the journal
has no issue numbers, as with SSCL).

## The raw-record cache

Every successful fetch writes its raw API records to
`cache/<id>/records/<year>.json`. That makes a parser change cheap:

```bash
python main.py --conference all --reparse     # rebuild JSON offline, no network
```

Without it, changing a front-matter rule meant a ~27-minute re-scrape of all
eleven sources and another few thousand requests at IEEE. With it, the same
change is re-applied in seconds and IEEE is not touched at all. Re-fetch only
when you actually want newer records.

## Resumability

- A year is skipped if `output/<id>/json/<year>.json` exists, unless
  `--overwrite` (or `--force-refresh`, which now implies it) is given.
- Affiliation lookups are cached in `cache/<id>/affiliations.json` and flushed
  every 50 fetches, so an interrupted enrichment loses at most 50 lookups.
- `update_database.py` re-fetches only recent years by default and fills gaps
  in older ones; `--full` forces everything.

## Where to make a change

| You want to… | Change |
|---|---|
| Add a source | `CONFERENCES` in `config.py`; pick a discovery mode (see `docs/02`). |
| Stop something being treated as a paper | `SKIP_TITLES` / `SKIP_PREFIXES` / `SKIP_PATTERNS` / `FRONT_MATTER_ABSTRACTS` in `parser.py` (see `docs/03`), then `tools/audit_front_matter.py`. |
| Fix garbled old text | `SPL_ENTITIES` in `textclean.py`, then `--reparse`. |
| Change how sessions are detected | `SESSION_HEADER_RE` / `CICC_SESSION_TRAILER_RE` in `parser.py`. |
| Change the look of the site | `templates/_styles.css.j2` (shared) or the page template. |
| Change mark/like/note behaviour | `templates/_scripts.js.j2` and `serve.py`. |
| Change what is synced to iCloud | `sync_to_icloud` in `update_database.py`. |

After any of these, check [`../CODEMAP.md`](../CODEMAP.md) for which docs need updating.
