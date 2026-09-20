# ONGOING

Active threads only. Delete a section the moment its thread finishes — use
`git log` for history. No review badge on this file by convention.

Last updated: 2026-09-20.

---

## Thread: affiliation backfill

**Status:** mechanism built and working; the corpus is mostly still empty.

Author affiliations are not in the search API — they need one extra request
per paper against `/rest/document/<articleNumber>/authors` (~0.7 s). A full
backfill of ~57k papers is roughly **17 hours** of wall clock, so it runs as a
separate, resumable, cached pass rather than part of the scrape.

Until a year has been enriched, its author names simply show without a
tooltip, which is the intended degradation.

Action items:

- [ ] Decide how much to backfill. Options: newest 2–3 years only (fast,
      covers what you read most), or let it grind through everything over a
      few evenings.
- [ ] Run it in chunks — it is resumable and re-running only fetches what is
      still missing:
      ```
      update.bat --affiliations 1000
      ```
      or per source:
      ```
      D:\anaconda3\python.exe main.py --conference isscc --enrich-affiliations --affiliation-limit 1000
      ```

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
