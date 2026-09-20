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
update.bat --conference jssc    # one source only
```

**Use `--full` after any change to `parser.py`** — filtering and session rules
only take effect on a re-parse.

## Browsing with marks saved to disk

```bash
python serve.py            # http://localhost:8800, opens a browser
```

Marks made here are written straight to `userdata/annotations.json`. Opening
`site/index.html` from disk also works, but then marks stay in that browser
until you press **Export marks** (see `04-viewer-and-marks.md`).

## iCloud

Target: `C:\Users\Yi Shen\iCloudDrive\IC_Design_Materials\Paper_Collection`

- Synced by default: `site/` (the browsable viewer) and `userdata/`
  (your marks). Add `--sync-data` to include `output/`.
- **Changed files only.** Every candidate is compared by content hash
  (size first, then BLAKE2b), so a rebuild that produces byte-identical HTML
  copies nothing. This is deliberate: handing iCloud tens of thousands of
  no-op writes is how sync conflicts start.
- The copy runs **once, at the end** — never per source or per year.

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
A front-matter rule is too broad. Find the offending pattern in `parser.py`,
tighten it, and re-run the sweep in
`scratch/2026-09-20-front-matter-audit.md` before committing.

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
3. Scrape 2–3 years first and inspect the JSON.
4. Check session parsing and front-matter filtering on those years.
5. Run the full range, then rebuild the site and master index.
6. Update `docs/02-data-sources.md` and `AGENTS.md`.
