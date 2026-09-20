# DEV LOG - IEEE Xplore Scraper

This file is a maintenance log + implementation guide for future agent edits.
It captures how the project currently works, what changed over time, and where
to modify behavior safely.

## 1) Project Purpose

Collect IEEE Xplore proceedings/journal data into structured JSON/CSV and build
a static local HTML viewer.

Primary pipeline:
1. Discover publication numbers (or use fixed mapping).
2. Fetch records from IEEE REST search API.
3. Parse records into year/session/paper structure.
4. Validate + export.
5. Build HTML (`site/<conference>/...`) and master index (`site/index.html`).

## 2) Current Supported IDs

Configured in `config.py` under `CONFERENCES`:

- `isscc` (conference)
- `rfic` (conference)
- `cicc` (conference)
- `vlsi` (conference; special multi-series handling)
- `jssc` (journal, fixed punumber)
- `tcas1` (journal, fixed punumber 8919)
- `tcas2` (journal, fixed punumber 8920)
- `tmtt` (journal, fixed punumber 22)

Note: README may lag behind actual config. `config.py` is source of truth.

## 3) Key Files and Responsibilities

- `main.py`
  - CLI entrypoint and workflow orchestration.
  - Flags: scrape / validate / export / html build.

- `config.py`
  - `ScraperConfig` dataclass.
  - Per-conference definitions.
  - Journal vs conference behavior switches.
  - `year_to_pubs` supports deterministic year->multiple-pub mapping.

- `scraper.py`
  - API calls + retry/rate limit.
  - Year discovery.
  - Full record retrieval (`_fetch_all_records_for_year`).
  - Journal early-access extraction and save.
  - Supports comma-separated publication numbers per year (merged records).

- `parser.py`
  - Converts raw records into `ConferenceYear -> Session -> Paper`.
  - Filters front matter.
  - Session assignment logic.
  - Conference order heuristics and prefix-aware paper/session handling.

- `validation.py`
  - Structural checks and summary output.

- `html_builder.py`
  - Year HTML + conference index HTML + master index HTML.
  - Journal `early_access.json` -> `early_access.html` and special index card.

- `templates/*.j2`
  - UI templates for per-year pages, per-conference index, global index.

## 4) IEEE API Usage Model

Endpoint:
- `POST https://ieeexplore.ieee.org/rest/search`

Important payload fields:
- `punumber` (publication number filter)
- `ranges: ["YYYY_YYYY_Year"]` (year filter, used especially for journals)
- `sortType: "vol-only-seq"` (record order)
- `rowsPerPage`, `pageNumber`

The site is SPA; direct HTML scraping is intentionally avoided.

## 5) Special Handling Implemented

### 5.1 Journals (JSSC / TCAS-I / TCAS-II / TMTT)

- Use fixed punumber from config (no yearly discovery needed).
- Year filtered via `ranges`.
- Group by issue in parser.
- Early access records are separated from normal year/issue pages:
  - moved out of `<year>.json` sessions
  - aggregated into `output/<id>/json/early_access.json`
  - rendered as `site/<id>/early_access.html`
  - appears as top-level item in conference index.

### 5.2 Front Matter Filtering

`parser.py` contains skip titles/patterns for non-paper records (editorials,
society info, covers, TOC, etc.). Keep extending these lists when needed.

### 5.3 ISSCC Session Numbering Robustness

ISSCC had ordering/assignment issues in some years (notably 2025). Fixes:
- Better conference record-order chooser (original order vs page sort).
- Session inference uses paper title prefix when available (e.g. `17.5`).
- Session creation can be updated when proper header appears later.

### 5.4 VLSI (Critical)

VLSI is not one uniform series across all years.

- Pre-2022: separate proceedings each year:
  - Symposium on VLSI Circuits
  - Symposium on VLSI Technology
- 2022+: merged as Symposium on VLSI Technology and Circuits.

To avoid wrong matches (VLSI-DAT, VLSI-TSA, VLSI-SoC, etc.), `vlsi` uses
deterministic `year_to_pubs` mapping in `config.py` and `scraper.py` merges
records from all listed pub numbers for each year.

This replaced fuzzy search-only discovery for VLSI.

## 6) Data Locations

- JSON: `output/<conference_id>/json/<year>.json`
- CSV: `output/<conference_id>/csv/<year>.csv`
- Combined JSON/CSV + validation summary in same folders.
- HTML year pages: `site/<conference_id>/year_<year>.html`
- Conference index: `site/<conference_id>/index.html`
- Global index: `site/index.html`

## 7) Common Commands

### Full scrape (example VLSI)

```bash
python main.py --conference vlsi --start-year 2000 --end-year 2026 --overwrite
python main.py --conference vlsi --build-html-only
```

### Build master index only

```bash
python -c "from html_builder import build_master_index; from config import CONFERENCES; from pathlib import Path; build_master_index(Path('site'), list(CONFERENCES.keys()))"
```

### Journal example

```bash
python main.py --conference tcas1 --start-year 2000 --end-year 2026 --overwrite
python main.py --conference tcas1 --build-html-only
```

## 8) Safe Modification Checklist (for agents)

When asked to modify behavior:

1. Read `config.py`, `scraper.py`, `parser.py`, `html_builder.py`.
2. Confirm whether request is conference-specific, journal-specific, or global.
3. Prefer deterministic mapping (`year_to_pubs`) if discovery ambiguity exists.
4. After edits:
   - run target conference scrape for a small range first,
   - then full requested range,
   - then `--build-html-only`.
5. Spot-check at least:
   - one early year,
   - one mid year,
   - latest year,
   - known problematic year (ISSCC 2025, VLSI 2021/2022 boundary).
6. Rebuild `site/index.html` if conference set changed.

## 9) Known Pitfalls

- CLI flag is `--build-html-only` (not `--html-only`).
- API search results can include similarly named but wrong conferences.
- `conference_name` field in papers may not reliably distinguish merged tracks;
  publication mapping is more reliable than display text.
- 2026 may have partial/no data depending on IEEE availability date.

## 10) If Future User Asks for New Conference/Journal

Recommended approach:

1. Add entry to `CONFERENCES` in `config.py`.
2. Decide discovery mode:
   - `fixed_punumber` for journals,
   - `year_to_pubs` if ambiguous conference family,
   - regular search discovery if unique and stable.
3. Run scrape for a narrow range first (2-3 years).
4. Validate output and session parsing quality.
5. Run full range and regenerate HTML + master index.

