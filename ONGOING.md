# ONGOING

Active threads only. Delete a section the moment its thread finishes — use
`git log` for history. No review badge on this file by convention.

Last updated: 2026-09-20.

---

## Thread: affiliation backfill

**Status:** RUNNING since 2026-09-20 17:53. Measured throughput **1.11
papers/sec**, so ~**15 hours** for all 59,463 papers.

Author affiliations are not in the search API — each paper needs its own
request to `/rest/document/<articleNumber>/authors`. Until a year is enriched,
its author names show without the hover tooltip, which is the intended
graceful degradation.

Work is ordered **newest year first across all nine sources at once**, not
source by source, so whatever is done is the part you would actually read.

- Progress: `cache/affiliation_progress.json` (percent, last year/source).
- Log: the run's stdout; each source also caches to
  `cache/<source>/affiliations.json`, flushed every 50 lookups.

**Safe to stop at any time** — a kill loses at most 50 requests. To resume, or
to continue it on another evening:

```
D:\anaconda3\python.exe tools/backfill_affiliations.py
D:\anaconda3\python.exe tools/backfill_affiliations.py --from-year 2020   # recent only
D:\anaconda3\python.exe tools/backfill_affiliations.py --budget 2000      # a bounded chunk
```

Action items:

- [ ] Let it run, or stop it and do it in chunks — either is fine.
- [ ] Once a decent chunk is done, rebuild and re-sync so the tooltips appear:
      `update.bat --no-scrape`.

## Thread: marks across machines

**Status:** working on this PC; the other-machine path needs a decision.

On this PC, `python serve.py` saves every like/mark/note straight to
`userdata/annotations.json`, and `update.bat` syncs that file to iCloud.

Opening the site from the iCloud folder on **another** machine is `file://`,
where a browser cannot write to disk. Marks made there live in that browser
until you press **Export marks** and drop the file back into iCloud
`userdata/`, which the next update run merges.

Action items:

- [ ] Confirm whether you actually mark papers on machines other than this PC.
      If yes, say so and the options are: run `serve.py` there too (needs
      Python), or accept the export/import step.
- [ ] Decide whether `userdata/annotations.json` should also be tracked in
      git. It is currently ignored, to keep the repo free of merge conflicts
      over your personal data; tracking it would give a second sync path.

## Thread: review of the 2026-09-20 rework

**Status:** waiting on you.

Every doc written in this pass carries a ⏳ **Unreviewed** badge. The code
changes are on two commits after the `fcb9f11` baseline, so
`git diff fcb9f11..HEAD` shows exactly what changed against the original.

Action items:

- [ ] Review the new docs and tell me which to flip to 👀 Glanced or
      ✅ Confirmed: `README.md`, `AGENTS.md`, `CODEMAP.md`, `docs/01`–`docs/05`.
- [ ] Sanity-check a few year pages in the browser — particularly that the
      paper-count drops are all front matter and not real papers
      (`tools/audit_front_matter.py` prints the longest removed titles).
- [ ] Confirm what should go to iCloud: `site/` + `userdata/` by default, or
      also `output/` (add `--sync-data`, ~282 MB more).
