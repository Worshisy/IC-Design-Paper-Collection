# AGENTS.md — IEEE Paper Collection workspace

> **Review status:** ⏳ Unreviewed *(default; update when Yi reviews)*
>
> ✍️ Claude-authored (2026-09-20). Shared coordination log for every agent
> working in this tree — read it before doing anything else, and append to it
> rather than restructuring it.

---

## 1. What this workspace is

A scraper + static viewer for IEEE Xplore paper metadata across 9 sources
(4 conferences, 5 journals), producing JSON/CSV datasets and a browsable
offline HTML site. The dataset is shared through iCloud; the code through
GitHub.

- **Remote:** https://github.com/Worshisy/IC-Design-Paper-Collection.git
- **iCloud target:** `C:\Users\Yi Shen\iCloudDrive\IC_Design_Materials\Paper_Collection`
- **Python:** 3.11+ required (`dataclass(slots=True)`). On Yi's PC the working
  interpreter is `D:\anaconda3\python.exe` (3.12.3). The `python` on PATH is
  **3.9 and cannot run this project**.

## 2. Workspace map

```
log_paper/
├── README.md                 ✍️ orientation + quick start
├── AGENTS.md                 ✍️ this file — canonical state, gotchas, handoffs
├── ONGOING.md                ✍️ active threads (delete sections as they finish)
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
├── templates/
│   ├── _styles.css.j2        ✍️ shared CSS
│   ├── _scripts.js.j2        ✍️ shared JS (theme, density, marks)
│   ├── year.html.j2          ✍️ rewritten
│   ├── index.html.j2         ✍️ rewritten
│   └── master_index.html.j2  🟦 conference picker
├── docs/                     ✍️ formal reference notes, numbered
├── scratch/                  ✍️ dated ad-hoc findings
├── userdata/annotations.json ✏️ YI'S DATA — never regenerate, only merge
├── output/<id>/{json,csv}/   generated dataset (git-ignored)
├── site/<id>/                generated viewer (git-ignored)
└── cache/<id>/               affiliation cache (git-ignored)
```

Authorship key: 🟦 pre-existing (author unknown — the tree had no git history
before 2026-09-20) · ✏️ Yi's data/edits · ✍️ Claude-authored.

## 3. Hard rules for this tree

1. **`userdata/annotations.json` is Yi's data.** Likes, marks and notes live
   there, keyed by IEEE article number. No scrape, rebuild or sync may
   overwrite it — merge per paper, newest `updated` timestamp wins. It is the
   one file a database refresh must leave alone.
2. **Never commit the dataset — `output/`, `site/`, `cache/`, `userdata/` or
   the PDFs.** This is a *legal* constraint, not a size one: those trees hold
   IEEE paper metadata and abstracts, and republishing them in a public
   GitHub repo is a copyright problem. **The repo is scripts and docs only.**
   The dataset stays private and travels via iCloud, and is regenerable with
   `update.bat`. Before any push, confirm `git status` shows no data files.
3. **iCloud writes are expensive.** Sync runs once, as the last step, and
   copies only files whose content hash changed. Do not add per-year or
   per-source syncing.
4. **Numbers in docs must come from a run you actually did.** Every figure in
   `docs/` and `scratch/` traces to measured output; re-measure rather than
   carrying a number forward.

## 4. Gotchas discovered the hard way

- **Console encoding.** Python's stdout on this PC defaults to **GBK**; any
  script printing a paper title dies with `UnicodeEncodeError`. Always set
  `PYTHONIOENCODING=utf-8` (`update.bat` does). Mojibake seen in a terminal is
  a console artifact — the stored JSON is clean UTF-8.
- **`select_autoescape(["html"])` does nothing** for `*.html.j2` templates: it
  matches the *final* extension only. Autoescape was silently off for the
  life of the project. It is now `("html", "xml", "j2")`.
- **The search API has no affiliations.** `POST /rest/search` returns author
  names and IDs only. Affiliations need `GET /rest/document/<articleNumber>/authors`,
  one request per paper (~0.7 s). Hence the resumable
  `--enrich-affiliations` pass and `cache/<id>/affiliations.json`.
- **`articleContentType` cannot identify front matter.** Every RFIC 2024
  record — cover page, TOC and real papers alike — reports
  `"Conference Paper"`. Front matter can only be detected from the title.
- **RFIC and VLSI have no session data at all** in the API; a single "General"
  session is the honest result, not a bug. CICC opens each session with an
  untitled invited talk, which is not machine-distinguishable from a paper.
  Only ISSCC exposes real `Session N Overview:` headers.
- **A performance figure can look like a paper number.** VLSI 2024's
  `"122.7 TOPS/W Stdcell-Based DNN Accelerator"` created session 122. Prefix
  inference now requires the year to contain at least one real session header.
- **Journal Early Access is shared across years.** Scraping one year used to
  rewrite the whole `early_access.json`; it now merges per year.

## 5. Project state

See `ONGOING.md` for what is in flight. The dataset counts after the
2026-09-20 rebuild are in `docs/02-data-sources.md`.

## 6. Handoff log

### 2026-09-20 — Claude
Audited the project (no git history existed; `git init` done, code-only
`.gitignore`). Ran every code path against the live API to confirm behaviour
before changing anything. Fixed: generic front-matter filtering, the VLSI
false-positive session, Early Access clobbering, Jinja autoescape, embedded
JSON escaping, ISSCC-hardcoded defaults, import-time directory side effects,
unused imports. Added: per-author affiliation fetching, the like/mark/note
system, a responsive non-truncating viewer, `update.bat` + `update_database.py`,
`serve.py`. Rewrote both page templates and extracted shared CSS/JS partials.
Full re-scrape of all 9 sources run afterwards.

A Sonnet style-review pass ran over the original code; its findings are
recorded in `scratch/2026-09-20-style-review.md` with what was and was not
acted on.
