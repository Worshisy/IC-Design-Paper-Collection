# Overnight review checklist

Things from the overnight run that want your eyes. Tick as you go; delete a
run's section once you have been through it.

---

## Run: 2026-09-20 → 21 — "fully usable HTML, all issues cleaned up"

### 1. Decisions I made on your behalf

You were asleep, so these were judgement calls. Each is reversible.

- [ ] **Editorial content kept** (you chose this before going quiet): guest
      editorials, special-issue introductions, corrections/errata,
      comments/replies, in memoriam, retraction notices. Only pure boilerplate
      was dropped. If you would rather have a papers-only list, one flag flips it.
- [ ] **ESSERC devices split is a fixed list, not a rule.** A Sonnet pass read
      all 93 sessions' titles and produced an explicit (year, session) list in
      `esserc_tracks.py`. Worth a skim — it is the one place a wrong call
      silently drops real circuits papers. 2024: −11 sessions/48 papers.
      2025: −8/47.
- [ ] **VLSI Technology split for 2022/2023/2024/2026** done the same way, by
      classifying 944 titles, because those years ship no usable Circuits
      programme. Check the per-year survivor counts look like a plausible
      Circuits symposium (~100–140).
- [ ] **Plenary sessions are named "Plenary 1"**, not after the speaker.
      ESSCIRC 2024 was producing sessions called "Luca Benini".

### 2. Things I could NOT fix (and why)

- [ ] **ESSCIRC 2020 missing** — no such publication in IEEE Xplore. Probably
      the virtual year. Nothing to scrape.
- [ ] **CICC 2016 missing** — probed four ways, with a working 2017 control.
      Genuinely not indexed.
- [ ] **TCAS-I 2008 Issue 12 missing** — absent from IEEE's own response.
- [ ] **Years that keep one "General" session** — IEEE publishes no
      machine-readable programme for them. Listed in `ONGOING.md`. These are a
      data limitation, not a bug; I did not invent structure for them.
- [ ] **`IoT % Security`** (ISSCC 2023) and similar oddities are IEEE's own
      metadata. I left them rather than silently "correcting" the source.

### 3. Please spot-check in the browser

- [ ] **Session codes** now show what the proceedings printed (`Mo1B`,
      `Session 12`, `61.3`) instead of a sequence number — this was your
      request, worth confirming it reads right on RFIC and ISSCC.
- [ ] **A year from each source** end to end, looking for anything that is not
      a paper.
- [ ] **Author hover** shows affiliations on years that have been enriched
      (newest years first; the backfill is incremental).
- [ ] **Marks** (★ / mark / note) survive a rebuild — they live in
      `userdata/annotations.json`, outside the dataset.

### 4. Numbers to sanity-check

- [ ] Per-source paper counts in `docs/02-data-sources.md` — particularly
      **VLSI** (Circuits-only, so roughly half the full symposium) and
      **ESSCIRC/ESSERC**.
- [ ] `output/<source>/csv/validation_summary.csv` if you want the per-year
      detail.

### 5. New files worth knowing about

- [ ] `toc_sessions.py` — recovers sessions from the printed programme.
- [ ] `esserc_tracks.py` — the ESSERC circuits/devices split.
- [ ] `textclean.py` — legacy markup and entity decoding.
- [ ] `tools/audit_front_matter.py` — run this after ANY change to the filter
      rules; it has caught three of my own false positives.
- [ ] `tools/backfill_affiliations.py` — resumable affiliation fetcher.

### 6. Still running / unfinished

- [ ] **Affiliation backfill** — resumable, was at ~47%. Re-run
      `python tools/backfill_affiliations.py` whenever; it only fetches what is
      still missing.
- [ ] **Unassigned buckets** — papers the programme did not list. Reduced but
      not zero; see `ONGOING.md`.
