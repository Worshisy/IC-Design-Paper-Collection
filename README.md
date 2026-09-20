# IC Design Paper Collection

> **Review status:** ⏳ Unreviewed *(default; update when Yi reviews)*
>
> ✍️ README authored by Claude (2026-09-20). File-level authorship is marked
> in [`AGENTS.md`](AGENTS.md).

Scrapes IEEE Xplore paper metadata for **9 sources** (4 conferences,
5 journals), exports JSON/CSV, and builds a fast offline HTML viewer with
search, author affiliations on hover, and your own likes / marks / notes.

---

## Update the database — one click

**Double-click `update.bat`.**

It merges your marks, refreshes recent years, validates, rebuilds the site,
and copies changed files to iCloud — in that order, with your marks never
touched. Details in [`docs/05-operations.md`](docs/05-operations.md).

```bash
update.bat                    # normal run
update.bat --full             # re-scrape every year from 2000 (~1 h)
update.bat --no-sync          # skip the iCloud copy
update.bat --affiliations 500 # also fetch author affiliations
```

## Browse

```bash
python serve.py               # http://localhost:8800 — marks save to disk
```

Or open `site/index.html` directly. Both work; only the server saves marks
automatically (see [`docs/04-viewer-and-marks.md`](docs/04-viewer-and-marks.md)).

---

## What you get

- **Year pages** grouped by session (or by issue, for journals), with a filter
  box and a liked-only toggle.
- **Search across every paper** of a source, by title/abstract, author, year,
  or your own mark.
- **Nothing truncated** — titles, abstracts and author lists show in full, and
  the layout reflows from a wide desktop down to a phone.
- **Hover an author** to see their affiliation.
- **★ like, a mark, and a note** on any paper, kept in
  `userdata/annotations.json` and synced through iCloud. A database update
  never touches them.
- Dark mode, three text sizes, MathJax for `$…$` in titles.

## Sources

| Conferences | Journals |
|---|---|
| ISSCC, RFIC, CICC, VLSI | JSSC, SSCL, TCAS-I, TCAS-II, TMTT |

Coverage is 2000–present (SSCL from 2018). Per-source counts and quirks are in
[`docs/02-data-sources.md`](docs/02-data-sources.md).

---

## Layout

```
log_paper/
├── update.bat  update_database.py   one-click refresh + iCloud sync
├── serve.py                         local server so marks save to disk
├── main.py                          the underlying CLI
├── config.py  scraper.py  parser.py  models.py  validation.py  html_builder.py
├── templates/                       page templates + shared CSS/JS
├── tools/audit_front_matter.py      regression check for the filter rules
├── docs/                            reference notes — start at docs/README.md
├── scratch/                         dated working notes
├── userdata/annotations.json        YOUR marks (never regenerated)
├── output/<source>/{json,csv}/      the dataset          (not in git)
├── site/<source>/                   the viewer           (not in git)
└── cache/<source>/                  affiliation cache    (not in git)
```

**The GitHub repo holds scripts and docs only — never the dataset.**
`output/`, `site/`, `cache/` and `userdata/` are git-ignored deliberately:
they contain IEEE paper metadata and abstracts, which must not be
republished publicly. The data stays private and syncs through iCloud; the
code syncs through GitHub. Anyone cloning the repo regenerates the dataset
themselves with `update.bat --full`.

## Setup on a new machine

```bash
git clone https://github.com/Worshisy/IC-Design-Paper-Collection.git
cd IC-Design-Paper-Collection
pip install -r requirements.txt
update.bat --full            # first run builds everything from scratch
```

**Python 3.11+ is required.** On Yi's PC the working interpreter is
`D:\anaconda3\python.exe` (3.12.3); the `python` on PATH is 3.9 and will fail.

## Documentation

| Read | For |
|---|---|
| [`AGENTS.md`](AGENTS.md) | Workspace state, hard rules, gotchas. **Agents read this first.** |
| [`docs/README.md`](docs/README.md) | Reference notes, in reading order. |
| [`ONGOING.md`](ONGOING.md) | What is currently in flight. |
| [`CODEMAP.md`](CODEMAP.md) | Which docs to update when a given file changes. |
| [`DEV_LOG.md`](DEV_LOG.md) | The earlier maintenance log, kept for history. |
