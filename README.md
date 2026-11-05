# IC Design Paper Collection

> **Review status:** ⏳ Unreviewed *(default; update when Yi reviews)*
>
> ✍️ README authored by Claude (2026-09-20). File-level authorship is marked
> in [`AGENTS.md`](AGENTS.md).

Scrapes IEEE Xplore paper metadata for **11 sources** (6 conferences,
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

On Yi's PC it already runs at login on port 18817, reachable on the home
LAN (Startup shortcut "Paper viewer (LAN 18817)").

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
| ISSCC, RFIC, CICC, ESSCIRC, VLSI, A-SSCC | JSSC, SSCL, TCAS-I, TCAS-II, TMTT |

Coverage is 2000–present (JSSC from 1995, A-SSCC from 2005, SSCL from 2018). Per-source counts and quirks are in
[`docs/02-data-sources.md`](docs/02-data-sources.md).

---

## Layout

```
log_paper/
├── README.md                 ✍️ orientation + quick start
├── AGENTS.md                 ✍️ rules, current state, pitfalls (agents read first)
├── ONGOING.md                ✍️ open threads, rewritten in place
├── DONE.md                   ✍️ closed threads, 3 lines each
├── CODEMAP.md                ✍️ code file -> the docs that describe it
├── DEV_LOG.md                🟦 pre-existing maintenance log (earlier agent)
├── update.bat                ✍️ ONE-CLICK update entry point
├── update_database.py        ✍️ refresh -> validate -> build -> iCloud sync
├── serve.py                  ✍️ local server so paper marks save to disk
├── main.py                   🟦 CLI (edited ✏️)
├── config.py                 🟦 sources + ScraperConfig (edited ✏️)
├── scraper.py                🟦 REST API access (edited ✏️)
├── parser.py                 🟦 records -> Year/Session/Paper (edited ✏️)
├── models.py                 🟦 pydantic dataclasses (edited ✏️)
├── validation.py             🟦 structural checks + CSV export (edited ✏️)
├── html_builder.py           🟦 Jinja rendering (edited ✏️)
├── toc_sessions.py           ✍️ recovers sessions from the printed programme
├── session_overrides.py      ✍️ hand-curated session assignments (see docs/06)
├── textclean.py              ✍️ legacy markup + entity decoding
├── esserc_tracks.py          ✍️ ESSERC circuits/devices split
├── vlsi_tracks.py            ✍️ VLSI Circuits/Technology split
├── tools/
│   ├── audit_front_matter.py      ✍️ is each record a paper?
│   ├── audit_session_overrides.py ✍️ does every override still match?
│   ├── audit_session_contents.py  ✍️ do a session's papers fit its name?
│   ├── audit_device_tracks.py     ✍️ is the track split complete and live?
│   ├── backfill_affiliations.py   ✍️ resumable affiliation fetcher
│   ├── restore_abstracts.py       ✍️ resumable full-abstract fetcher
│   ├── repair_abstract_markup.py  ✍️ re-cleans JATS/MathML markup in stored abstracts
│   └── refresh_citations.py       ✍️ IEEE citation counts, all years
├── data/
│   ├── session_overrides.tsv      ✏️ curated; DATASET, do not publish
│   ├── programmes.tsv             ✏️ programmes hosted outside Xplore
│   └── vlsi_technology_papers.txt ✏️ curated track list
├── templates/
│   ├── _styles.css.j2        ✍️ shared CSS
│   ├── _scripts.js.j2        ✍️ shared JS (theme, density, marks)
│   ├── year.html.j2          ✍️ rewritten
│   ├── index.html.j2         ✍️ rewritten
│   └── master_index.html.j2  🟦 conference picker
├── docs/                     ✍️ formal reference notes, numbered
├── surveys/                  ✍️ private companion repo (topic surveys, literature reviews); git-ignored here
├── scratch/                  ✍️ dated ad-hoc findings
├── userdata/annotations.json ✏️ YI'S DATA — never regenerate, only merge
├── output/<id>/{json,csv}/   generated dataset (git-ignored)
├── site/<id>/                generated viewer (git-ignored)
└── cache/<id>/               affiliation cache (git-ignored)
```

Authorship key: 🟦 pre-existing (author unknown; the tree had no git history
before 2026-09-20) · ✏️ Yi's data/edits · ✍️ Claude-authored.

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
| [`AGENTS.md`](AGENTS.md) | Rules, current state, pitfalls. **Agents read this first.** |
| [`docs/README.md`](docs/README.md) | Reference notes, in reading order. |
| [`ONGOING.md`](ONGOING.md) | Open threads. |
| [`DONE.md`](DONE.md) | Closed threads, newest first. |
| [`CODEMAP.md`](CODEMAP.md) | Which docs to update when a given file changes. |
| [`DEV_LOG.md`](DEV_LOG.md) | The earlier maintenance log, kept for history. |
