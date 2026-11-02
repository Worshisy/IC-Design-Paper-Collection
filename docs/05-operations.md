# 05 — Operations

> **Review status:** ⏳ Unreviewed *(default; update when Yi reviews)*
>
> ✍️ Claude-authored (2026-09-20).

## The one-click update

**Double-click `update.bat`.** That is the whole routine.

It runs, in order:

1. **Merge marks first.** Pulls `annotations.json` from iCloud, merges it with
   the local one (newest timestamp per paper wins), writes the result back to
   `userdata/`. Done before anything else so nothing downstream can lose it.
2. **Refresh the dataset.** Re-scrapes the last 3 years of every source —
   that is where IEEE still adds records — and fills in any missing older
   years. Older years already on disk are left alone.
3. **Validate and export.** Structural checks, per-year and combined CSV,
   `validation_summary.csv`.
4. **Rebuild the site**, including each source's `annotations.js` seed and the
   master index.
5. **Sync to iCloud**, last, copying only files whose content hash changed.

A source that fails is logged and skipped; the rest still complete.

### Options

```bash
update.bat                      # the normal run
update.bat --full               # re-scrape every year from 2000 (slow: ~1 h)
update.bat --no-sync            # skip the iCloud copy
update.bat --no-scrape          # rebuild + sync from existing JSON
update.bat --sync-data          # also mirror output/ (JSON+CSV), not just site/
update.bat --affiliations 500   # also fetch affiliations, 500 papers per source
update.bat --citations          # also refresh every paper's citation count
update.bat --conference jssc    # one source only
```

**After changing `parser.py`, re-parse rather than re-scrape:**

```bash
D:\anaconda3\python.exe main.py --conference all --reparse
```

That rebuilds every year's JSON from the cached raw records in
`cache/<id>/records/`, offline and in seconds. `--full` is only needed when
you want *newer records* from IEEE, not when you have changed how records are
interpreted.

## Browsing with marks saved to disk

```bash
python serve.py            # http://localhost:8800, opens a browser
```

Marks made here are written straight to `userdata/annotations.json`. Opening
`site/index.html` from disk also works, but then marks stay in that browser
until you press **Export marks** (see `04-viewer-and-marks.md`).

**On the home LAN.** `serve.py --host 0.0.0.0` listens on every address, so a
phone on the same network can open the viewer. Anyone on that network can then
change marks too: there is no login. On Yi's PC it starts at login, hidden, from
a Startup-folder shortcut, "Paper viewer (LAN 18817).lnk":

```powershell
D:\anaconda3\pythonw.exe serve.py --host 0.0.0.0 --port 18817 --no-browser
```

Port 18817 because 8817 and 8818 refuse a LAN bind on that PC ("address in
use", WinError 10048) while their loopback bind succeeds. Delete the shortcut
to stop the auto-start.

## iCloud

Target: `C:\Users\Yi Shen\iCloudDrive\IC_Design_Materials\Paper_Collection`

- Synced by default: `site/` (the browsable viewer) and `userdata/`
  (your marks). Add `--sync-data` to include `output/` (JSON + CSV, ~290 MB).
- **Layout**: the site goes to the **root** of the iCloud folder
  (`Paper_Collection/isscc/…`, `Paper_Collection/index.html`), matching the
  layout already in use there. Marks go to `Paper_Collection/userdata/`.
- **Changed files only, decided locally.** Each file's hash is compared
  against `cache/icloud_manifest.json` — a record of what was last copied —
  so an unchanged file is never even read back from iCloud. That matters:
  hashing the 107 MB site *out of* iCloud takes minutes, because files may be
  dehydrated placeholders that have to be downloaded first.
- **A run with no real changes copies nothing.** Verified: 0 files copied,
  253 left alone. `annotations.json` is only rewritten when a mark actually
  changes — stamping it with a fresh timestamp each run would alter it plus
  all nine `annotations.js` seeds, handing iCloud ten pointless writes every
  time.
- The copy runs **once, at the end** — never per source or per year.
- If iCloud ever gets out of step (files deleted there by hand), delete
  `cache/icloud_manifest.json` and the next run re-copies everything.

## Citation counts

Each paper's `citation_count` is IEEE Xplore's own count (the "Cited by
Papers" figure), not Google Scholar's. The search API returns it with every
record, so a refresh costs one request per 100 papers, not one per paper.

```bash
update.bat --no-scrape --citations                       # refresh all, rebuild, sync
D:\anaconda3\python.exe tools/refresh_citations.py --sources jssc,isscc
D:\anaconda3\python.exe tools/refresh_citations.py --older-than 1   # resume a killed run
```

The tool copies the new counts into the raw record cache and writes them
into the year files in place. It does not re-parse, so the curated session
layer cannot move. A year whose fetch fails keeps its old counts and is
listed at the end. The date each year was fetched is kept in
`output/citations_updated.json`, and the search page header shows the range.
A normal scrape also brings fresh counts for the years it re-fetches. The
CSV export picks the field up the next time a source is scraped.

## Full abstracts

IEEE's search API, which every record comes from, cuts abstracts at about
400 characters. `tools/restore_abstracts.py` fetches the full text, one
request per paper, 3 in parallel at the affiliation backfill's tested pace
(about 2 a second, so roughly 8 hours for the corpus), newest years first; it can be stopped and
resumed, and refuses to run alongside an affiliation backfill. Fetched text
is cached in `cache/<id>/abstracts_full.json` and re-applied by the scraper
on every refresh or re-parse. Progress: `cache/abstract_progress.json`;
log: `cache/abstract_restore.log`.

```bash
D:\anaconda3\python.exe tools/restore_abstracts.py
D:\anaconda3\python.exe tools/restore_abstracts.py --from-year 2020 --budget 500
```

Rebuild the site afterwards (`update.bat --no-scrape`) to show the full text.

The fetched text carries math markup. `clean_text` handles it (docs/03 §6),
but text stored before 2026-11-02 needs
`tools/repair_abstract_markup.py --dry-run`, then a run without
`--dry-run`. It re-cleans the cache and the year files in place, and refuses
to run while the restore holds its lock.

**Pacing.** The first run (2026-10-27) restored 46,363 papers in about 8.5
hours, then IEEE answered every request with HTTP 418. The script retried
for five days with nothing restored. A second run, through Yi's Mac, drew 418s
from its first minute; retries got past them, and it was blocked within the
hour. Since this is a one-off job, it now runs slow and safe: 1 worker, one
request every 2 s (`--interval`, `--workers`), one try per request. Any single
refusal (418/429/403, or no connection) doubles the interval, up to 16 s, and
pauses `--soft-minutes` (default 5). After 300 clean requests the interval
halves again. The gap between requests is random, 1-5 s, with a new seed every hour of
run time. The shared limiter in `utils.py` does the same for every other IEEE
job (scrape, affiliations, citations): 1-5 s between search requests
(0.45-2.25 s for author lookups), and a random 15-45 min rest after each
random 55-65 min of requests. Two more guards cover long runs:

- **Scheduled rest.** After a random 55-65 minutes of fetching it pauses a
  random 15-45 minutes. A short job never reaches the limit.
- **Block guard.** Three 418/429/403 answers in a row stop all workers. The
  script then waits, sends one test request, and resumes if it succeeds.
  Each failed test doubles the wait: 30, 60, 120 and 120 minutes. After
  `--max-pauses` failed tests (default 4) it saves its progress and exits
  with code 3. Re-run it later to resume.

## Running the tools directly

The `python` on PATH here is 3.9 and **cannot** run this project (it needs
3.11+ for `dataclass(slots=True)`). Use the Anaconda interpreter:

```bash
D:\anaconda3\python.exe main.py --conference isscc --start-year 2025 --end-year 2026 --overwrite
D:\anaconda3\python.exe main.py --conference all --build-html-only
D:\anaconda3\python.exe main.py --conference tmtt --validate-only
```

Always set `PYTHONIOENCODING=utf-8` first — see below.

## Troubleshooting

**`UnicodeEncodeError: 'gbk' codec can't encode character`**
Python's stdout defaults to GBK on this PC, and paper titles contain
characters it cannot represent. Set `PYTHONIOENCODING=utf-8`; `update.bat`
does this already. Garbled characters *in the terminal* are a console
artifact — check the JSON on disk before believing the data is corrupt.

**A year shows 0 papers**
IEEE may not have published it yet (common for the next calendar year), or
discovery failed. Check `output/<id>/json/<year>_errors.json`.

**Paper counts dropped after an update**
Expected as of 2026-09-20: front-matter filtering now removes covers, indexes
and mastheads that were previously counted as papers. See
`docs/02-data-sources.md` for the before/after figures.

**A real paper disappeared**
A front-matter rule is too broad. Run `tools/audit_front_matter.py`: its
"must NOT be filtered" cases exist for exactly this, and the sweep prints the
longest removed titles, where false positives hide. Tighten the pattern, add
the paper as a new unit case, then `--reparse`.

**Affiliation fetching is slow**
It is one request per paper by design. Use `--affiliation-limit` to work
through the backlog in sessions; the cache makes it resumable.

**Rate limiting / HTTP errors**
`rate_limit_seconds` (1.5 s) and `affiliation_rate_limit_seconds` (0.4 s) in
`config.py` throttle the two endpoints. Retries are exponential with 5
attempts. If IEEE starts rejecting requests, raise the delays rather than
adding concurrency.

## Adding a new source

1. Add an entry to `CONFERENCES` in `config.py`.
2. Choose a discovery mode (see `02-data-sources.md`): `fixed_punumber` for a
   journal, `year_to_pubs` when the name is ambiguous, plain search otherwise.
3. **Run discovery over every year of the range before scraping anything**,
   and print the publication title it finds for each. A year discovery misses
   is absent with no error. A-SSCC answers to three different names and no
   single one of them covers all 21 years.
4. **Read the title rules of the sources the new one resembles.** A-SSCC's
   title contains ISSCC's entire `title_contains`; ISSCC needed
   `title_excludes_any` before the two could coexist.
5. Scrape 2–3 years first and inspect the JSON.
6. Check session parsing and front-matter filtering on those years, then run
   `tools/audit_front_matter.py` — it reports what every rule would remove
   from every source, longest title first.
7. Run the full range, then `--toc-sessions` over all of it (judging the
   programme on two years is not judging it), then rebuild the site.
8. Update `docs/02-data-sources.md` and `AGENTS.md`.
