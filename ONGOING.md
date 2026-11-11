# ONGOING

Open threads, rewritten in place (`/Workflow:workspace-bootstrap`). A closed
thread moves to `DONE.md`. History is in git and `docs/07-history.md`.

## Backlog
- Dropped tutorials (found 2026-11-10): the front-matter title pattern `tutorials?$` (`parser.py:267`, meant for programme entries) also drops journal papers titled "…: A Tutorial": 31 real papers with authors and abstracts are missing (TCAS-II 21, TCAS-I 6, TMTT 2, JSSC 1, CICC 1; e.g. JSSC 2000 "Oscillator phase noise: a tutorial", TCAS-II 2024 10342829). Fix needs Yi's go: narrow the rule, then `--reparse` the affected years from the record cache (no IEEE requests). List: `tutorial_drops.py` output in the Claude session scratchpad.
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
