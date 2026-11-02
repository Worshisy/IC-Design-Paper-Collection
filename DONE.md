# DONE

Closed threads, newest first, 3 lines each. Results stay where the line
points; this file is an index. Created 2026-11-02 from the old `AGENTS.md`
handoff log (full text in [`docs/07-history.md`](docs/07-history.md) §2) and
the closed parts of `ONGOING.md`. Work after 2026-09-21 is not committed yet.

## 2026-11-02 · Full abstracts   (opened 2026-10-27, owner sy-paper-log)
Outcome: 56,475 of 62,209 stored abstracts now over 410 characters (was ~5,300); JATS/MathML markup cleaned (17,965 abstracts, 0 tags left); IEEE pacing guards added after a 5-day 418 block.
Shipped: uncommitted · Results: docs/05 §Full abstracts, docs/03 §6, AGENTS pitfalls 34-36 · Follow-ups: Backlog (14 unfetched, [c] review, tunnel)

## 2026-11-02 · Survey: ML in AMS/RF circuits since 2018   (opened 2026-11-02, owner sy-paper-log)
Outcome: `surveys/survey.py` pipeline built (reusable); 622 papers judged, 184 included + 2 borderline in `surveys/ml-ams-rf/out/ml-ams-rf.html` (git-ignored).
Shipped: uncommitted · Results: surveys/README.md, /Paper:field-glance cost table · Follow-ups: none

## 2026-10-22 · Citation counts   (opened 2026-10-22, owner Claude)
Outcome: every paper carries IEEE's `citationCount`; a "Cited" column and Sort → Citations in search; `tools/refresh_citations.py` and `update.bat --citations`.
Shipped: uncommitted · Results: docs/05 §Citation counts, docs/07 §2 · Follow-ups: none

## 2026-10-12 · Every unassigned paper and flat year ("fix all")   (opened 2026-10-12, owner Claude)
Outcome: A-SSCC 143 → 0 unassigned and checked against print (183 mis-filed papers found); RFIC 2001-2006 and ESSCIRC 2003-04 given sessions; `_print_order`.
Shipped: uncommitted · Results: docs/06, docs/07 §2 · Follow-ups: ONGOING "sessions - what is left"

## 2026-10-12 · A-SSCC: all 21 years' sessions   (opened 2026-10-12, owner Claude)
Outcome: all 21 years recovered, by one sub-agent per year, from Xplore programmes, epapers2.org, VDEC and page images; 2025's programme was filed as a "Cover Page".
Shipped: uncommitted · Results: docs/06, docs/07 §2 · Follow-ups: none

## 2026-10-12 · A-SSCC added as the 11th source   (opened 2026-10-12, owner Claude)
Outcome: 2,118 papers 2005-2025 with affiliations; ISSCC `title_excludes_any`; four programme-item rules (79 audit cases pass).
Shipped: uncommitted · Results: docs/02, docs/07 §2 · Follow-ups: none

## 2026-09-22 · Global search page   (opened 2026-09-21, owner Claude)
Outcome: one search over every source, with affiliation scope and column, resizable columns, an abstract column, MathJax shipped in the site, and case and phrase fixes.
Shipped: uncommitted · Results: docs/04 · Follow-ups: Backlog "check search default columns"

## 2026-09-21 · Session recovery, track leaks, override table   (opened 2026-09-21, owner Claude)
Outcome: collapsed years 65 → 21, unassigned 573 → 1; four audit tools; affiliations 99.2%.
Shipped: c7a7c64, f41824c, e27c9a9 · Results: docs/06, docs/07 §2 · Follow-ups: ONGOING "session-contents findings"

## 2026-09-20 · Audit and rebuild of the inherited scraper   (opened 2026-09-20, owner Claude)
Outcome: git history started; front-matter, Early Access, autoescape and markup fixes; affiliations; marks; one-click update and sync.
Shipped: fcb9f11..aefd168 · Results: docs/01-05, docs/07 §2 · Follow-ups: none
