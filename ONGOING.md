# ONGOING

Open threads, rewritten in place (`/Workflow:workspace-bootstrap`). A closed
thread moves to `DONE.md`. History is in git and `docs/07-history.md`.

## Backlog
- TCAS-II record gap (found 2026-11-10): 2024 holds exactly 1,000 papers (2022: 1,020) and misses e.g. the tutorial at vol. 71 p. 1663 (Xplore 10342829); the search paging likely stops at 1,000 records. Check `scraper.py` paging and re-fetch the year only with Yi's go (IEEE rule 7).
- Local commits wait for Yi's word to push: `git log --oneline origin/main..HEAD` (the dff7e35 review-notes endpoint plus doc-only commits, 2026-11-09).
- Literature-review work is tracked in the private companion repo: `surveys/ONGOING.md` and `surveys/scratch/_resume-*.md` (2026-11-06).
- Session-contents findings: 28 open from `tools/audit_session_contents.py` (parked 2026-11-04; `scratch/parked-threads.md`).
- Session decisions for Yi: 5 yes/no items (RFIC 2006 placement, CICC 2018 drops, `_print_order`, A-SSCC calls, A-SSCC 2020 cross-listing) (parked; `scratch/parked-threads.md`).
- Session known gaps: ESSCIRC 2005 programme, in-session order, A-SSCC 2024 codes, unchecked parser years, `# [c]` review (parked; `scratch/parked-threads.md`).
- VLSI 2024/2026 papers the saved programme drops (20 + 5), awaiting Yi's decision (parked; `scratch/parked-threads.md`).
- Cosmetic viewer items: orphaned SSCL Early Access page, its header text, master-index dark mode (parked; `scratch/parked-threads.md`).
- Yi reviews the `# [c]` code from the abstract and pacing work: `textclean.py`, `utils.py`, `config.py`, `scraper.py`, `tools/restore_abstracts.py`, `tools/repair_abstract_markup.py`, and `html_builder.py` (surveys index).
- 14 abstracts the 2026-11-01 restore could not fetch (4,717/4,731); re-run `tools/restore_abstracts.py` some day, it picks up only those.
- Check the search page's default columns and widths on the wide monitor (`COLUMNS` in `search.html.j2`).
