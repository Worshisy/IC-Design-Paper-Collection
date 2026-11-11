# DONE

Closed threads, newest first, 3 lines each. Results stay where the line
points; this file is an index. Created 2026-11-02 from the old `AGENTS.md`
handoff log (full text in [`docs/07-history.md`](docs/07-history.md) §2) and
the closed parts of `ONGOING.md`. Work up to 2026-11-02 is in 98aa16b.

## 2026-11-10 · Tutorial papers restored   (opened 2026-11-10, owner sy-paper-log)
Outcome: programme-listing title rules had dropped 35 papers (34 journal, 1 CICC) ("...: A Tutorial", "Tutorial: ...", "50 Years of ..."); `parser.py` keeps them now (`_is_tutorial_paper`), 34 restored by a journal `--reparse` with full abstracts and affiliations (fetched through the Mac), site rebuilt, iCloud synced; CICC restored from backup.
Shipped: this commit (local; push waits for Yi) · Results: docs/07-history.md §1 item 37, AGENTS pitfall 37, docs/03 · Follow-ups: Backlog CICC 2020 line; tutorials page in the private repo

## 2026-11-09 · Review notes endpoint in the viewer   (opened 2026-11-09, owner sy-paper-log)
Outcome: `serve.py` serves GET/POST `/api/review-notes`, so highlights and comments on review pages save to `userdata/review_notes.json` (merged per note, newest wins); the page script lives in the private repo (`surveys/review_notes.js`).
Shipped: dff7e35 (local, push waits for Yi) · Results: AGENTS.md §2 Viewer · Follow-ups: Backlog push line

## 2026-11-05 · Literature reviews moved to a private companion repo   (opened 2026-11-05, owner sy-paper-log)
Outcome: topic surveys and literature reviews now live in a private repo nested at `surveys/` (git-ignored); this repo's history was rewritten without them and force-pushed; their DONE entries moved there.
Shipped: this commit, history rewrite (old 16bce73 is now 98aa16b) · Results: AGENTS.md §2, .gitignore · Follow-ups: none

## 2026-11-02 · GitHub publication   (opened 2026-09-21, owner sy-paper-log)
Outcome: scripts and docs pushed; curated per-paper lists, programme text and agent outputs git-ignored with the dataset.
Shipped: c7a7c64, 98aa16b · Results: .gitignore, AGENTS rule 2 · Follow-ups: none

## 2026-11-02 · Full abstracts   (opened 2026-10-27, owner sy-paper-log)
Outcome: 56,475 of 62,209 stored abstracts now over 410 characters (was ~5,300); JATS/MathML markup cleaned (17,965 abstracts, 0 tags left); IEEE pacing guards added after a 5-day 418 block.
Shipped: 98aa16b · Results: docs/05 §Full abstracts, docs/03 §6, AGENTS pitfalls 34-36 · Follow-ups: Backlog (14 unfetched, [c] review, tunnel)

## 2026-10-22 · Citation counts   (opened 2026-10-22, owner Claude)
Outcome: every paper carries IEEE's `citationCount`; a "Cited" column and Sort → Citations in search; `tools/refresh_citations.py` and `update.bat --citations`.
Shipped: 98aa16b · Results: docs/05 §Citation counts, docs/07 §2 · Follow-ups: none

## 2026-10-12 · Every unassigned paper and flat year ("fix all")   (opened 2026-10-12, owner Claude)
Outcome: A-SSCC 143 → 0 unassigned and checked against print (183 mis-filed papers found); RFIC 2001-2006 and ESSCIRC 2003-04 given sessions; `_print_order`.
Shipped: 98aa16b · Results: docs/06, docs/07 §2 · Follow-ups: ONGOING "sessions - what is left"

## 2026-10-12 · A-SSCC: all 21 years' sessions   (opened 2026-10-12, owner Claude)
Outcome: all 21 years recovered, by one sub-agent per year, from Xplore programmes, epapers2.org, VDEC and page images; 2025's programme was filed as a "Cover Page".
Shipped: 98aa16b · Results: docs/06, docs/07 §2 · Follow-ups: none

## 2026-10-12 · A-SSCC added as the 11th source   (opened 2026-10-12, owner Claude)
Outcome: 2,118 papers 2005-2025 with affiliations; ISSCC `title_excludes_any`; four programme-item rules (79 audit cases pass).
Shipped: 98aa16b · Results: docs/02, docs/07 §2 · Follow-ups: none

## 2026-09-22 · Global search page   (opened 2026-09-21, owner Claude)
Outcome: one search over every source, with affiliation scope and column, resizable columns, an abstract column, MathJax shipped in the site, and case and phrase fixes.
Shipped: 98aa16b · Results: docs/04 · Follow-ups: Backlog "check search default columns"

## 2026-09-21 · Session recovery, track leaks, override table   (opened 2026-09-21, owner Claude)
Outcome: collapsed years 65 → 21, unassigned 573 → 1; four audit tools; affiliations 99.2%.
Shipped: c7a7c64, f41824c, e27c9a9 · Results: docs/06, docs/07 §2 · Follow-ups: ONGOING "session-contents findings"

## 2026-09-20 · Audit and rebuild of the inherited scraper   (opened 2026-09-20, owner Claude)
Outcome: git history started; front-matter, Early Access, autoescape and markup fixes; affiliations; marks; one-click update and sync.
Shipped: fcb9f11..aefd168 · Results: docs/01-05, docs/07 §2 · Follow-ups: none
