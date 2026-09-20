# IEEE Conference Proceedings Scraper & Static Viewer

Scrapes IEEE Xplore conference proceedings via the REST search API, validates
the dataset, exports JSON/CSV, and generates a static HTML site for local
browsing and search.

**Supported conferences:** ISSCC, RFIC, CICC (2000–2025+).

Targets **Python 3.11+**.

---

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS / Linux

pip install -r requirements.txt
```

---

## Quick start

### Scrape one conference (default: ISSCC)

```bash
# ISSCC 2000–latest
python main.py --conference isscc

# RFIC 2000–2025
python main.py --conference rfic --start-year 2000 --end-year 2025

# CICC 2000–2025
python main.py --conference cicc --start-year 2000 --end-year 2025
```

### Scrape all three conferences

```bash
python main.py --conference all --start-year 2000 --end-year 2025
```

### Build the static HTML site (after scraping)

```bash
# One conference
python main.py --conference rfic --build-html-only

# All conferences (also writes site/index.html as conference picker)
python main.py --conference all --build-html-only
```

Open `site/index.html` to choose a conference, then browse by year or use the search.

### Validate / export only (no scraping)

```bash
python main.py --conference rfic --validate-only
```

---

## CLI flags

| Flag | Description |
|------|-------------|
| `--conference {isscc,rfic,cicc,all}` | Conference to scrape or build (default: isscc) |
| `--start-year N` | First year (inclusive) to scrape |
| `--end-year N` | Last year (inclusive) to scrape |
| `--force-refresh` | Ignore cached data and re-fetch from API |
| `--overwrite` | Overwrite existing per-year JSON |
| `--build-html-only` | Skip scraping; build static HTML from existing JSON |
| `--validate-only` | Skip scraping; validate JSON and export CSVs |
| `--export-only` | Alias for `--validate-only` |
| `--input-json-dir DIR` | Custom directory with per-year JSON files |

---

## How it works

IEEE Xplore pages are JavaScript-rendered SPAs, so plain HTTP requests cannot
scrape the HTML directly. Instead, this project uses the **same REST API** that
the IEEE Xplore frontend calls:

```
POST https://ieeexplore.ieee.org/rest/search
```

### Workflow

1. **Discover years**: For each year in the target range, the scraper searches
   for the conference’s search term (e.g. ISSCC, RFIC, CICC) in that year. If
   the `publicationTitle` matches the conference’s `title_contains` string, the
   `publicationNumber` (used as `punumber` in the API) is recorded.

2. **Fetch all records**: Using the `punumber`, the scraper pages through the
   search API with `sortType: vol-only-seq` so records arrive in proceedings
   order. Each record contains the article title, authors, abstract, DOI, and
   a link to the paper page.

3. **Parse sessions and papers**: The parser detects session headers
   (e.g. "Session 2 Overview: Processors") and groups subsequent records under
   that session. Paper numbers are inferred sequentially (`2.1`, `2.2`, ...).
   If a title already contains a numeric prefix, the displayed number is stored
   separately and mismatches are logged.

4. **Validation & export**: The validator checks structural rules (session
   ordering, contiguous numbering, duplicates) and exports per-year JSON, CSV,
   combined files, and a validation summary.

5. **Static HTML**: Jinja2 templates render one HTML page per year with a
   searchable, sortable table and an index page listing all years.

---

## Output directory structure

Data and HTML are grouped by conference:

```
output/
├── isscc/
│   ├── json/                      # 2000.json, 2001.json, ... combined_all_years.json
│   └── csv/                       # per-year and combined CSVs
├── rfic/
│   ├── json/
│   └── csv/
└── cicc/
    ├── json/
    └── csv/

site/
├── index.html                     # conference picker (when using --conference all)
├── isscc/
│   ├── index.html                 # year list + search all papers
│   └── year_2025.html
├── rfic/
│   ├── index.html
│   └── year_*.html
└── cicc/
    ├── index.html
    └── year_*.html
```

If you previously used the single-conference layout (`output/json`, `output/html`), move existing data so ISSCC uses the new paths:

- `output/json/*` → `output/isscc/json/`
- `output/csv/*` → `output/isscc/csv/`
- `output/html/*` or `site/*` → `site/isscc/`

Then run `python main.py --conference isscc --build-html-only` to regenerate HTML under `site/isscc/`.

---

## Configuration

Conference definitions and paths are in `config.py`:

- `CONFERENCES` – dict of conference id → `name`, `search_term`, `title_contains` for API discovery.
- `get_config(conference_id)` – returns `ScraperConfig` with conference-specific paths and search settings.

Other defaults (in `ScraperConfig`):

- `search_api_url` – IEEE Xplore REST search endpoint.
- `year_min` – minimum year to include (default: 2000).
- `rate_limit_seconds` – delay between API calls (default: 1.5 s).
- `rows_per_page` – records per API page (default: 100).
- `max_retries`, `backoff_initial_seconds`, `backoff_max_seconds` – retry config.
- Output directory paths.

---

## HTML viewer features

Each `year_YYYY.html` page includes:

- **Summary panel**: total sessions, total papers, session jump chips.
- **Search box**: client-side filtering by any visible text.
- **Compact table** with sticky headers:
  - Session number and name (monospace numbers).
  - Paper number (monospace).
  - Clickable title (opens IEEE Xplore in a new tab).
  - Abstract (small font, wrapped, searchable).
  - Authors and affiliations.
- **Sortable columns**: session, paper number, title, authors.

All HTML is pure static — works from local files, no server needed.

---

## Validation rules

For each year:

- Year must be ≥ 2000.
- Session numbers must strictly increase.
- Paper numbers within each session must be contiguous (1, 2, 3, ...).
- No duplicate `paper_url` or `paper_number` within a year.
- Warnings for: empty title, empty abstract, empty author list.

The summary report includes: `num_sessions`, `num_papers`, `missing_title_count`,
`missing_abstract_count`, `missing_authors_count`, `numbering_mismatch_count`,
`duplicate_paper_url_count`, `duplicate_paper_number_count`,
`failed_paper_fetch_count`.

---

## Known assumptions

- **Session boundaries**: Papers belong to the current session until the next
  `"Session N ..."` header. Session headers are detected by regex.

- **Canonical paper numbering**: The `paper_number` is always inferred
  sequentially per session as `"{session}.{index}"`, starting at 1.
  The `displayed_paper_number` (if present in the title) is stored separately.

- **Displayed paper prefixes**: Some titles include an explicit number prefix
  (e.g. `"2.3 A 71.3mJ/Frame ..."`), others omit it entirely.
  The canonical number always uses the inferred sequence.
  Mismatches are logged as warnings.

- **Affiliations**: The search API does not always return per-author
  affiliations. The `affiliations` field may be empty; the structured
  author list is always populated when the API provides it.

- **Front matter**: Records titled "Front Cover", "Copyright Page", "Title
  Page", "Table of Contents", and "Awards" are skipped and not counted as
  papers.

---

## Adapting when IEEE Xplore changes

- **API endpoint**: If the search API moves, update `search_api_url` in
  `config.py`.

- **API payload**: If field names change (e.g. `punumber` → something else),
  update `scraper.py: _fetch_all_records_for_year()`.

- **Session header format**: If session titles change format, update
  `SESSION_HEADER_RE` in `parser.py`.

- **Skip titles**: If new front-matter types appear, add them to
  `SKIP_TITLES` in `parser.py`.

- **Debugging**: The per-year `_errors.json` files list papers with missing
  data. Increase logging to `DEBUG` in `utils.setup_logging()` for more
  detail.

---

## Run command

```bash
# Scrape, validate, export, then build HTML:
python main.py --start-year 2000 --end-year 2026
python main.py --build-html-only
```
