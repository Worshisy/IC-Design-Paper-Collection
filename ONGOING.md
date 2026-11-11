# ONGOING

Open threads, rewritten in place (`/Workflow:workspace-bootstrap`). A closed
thread moves to `DONE.md`. History is in git and `docs/07-history.md`.

## Backlog
- Audit `RECORD_CASES` now run (2026-11-10): "Plenary Speaker 1: Wireless spectrum challenges" (authorless) is expected filtered but the parser keeps it, also before today; fix `PROGRAMME_TITLE_RE` or drop the case (Yi).
- Conference teaching items are kept out of the log by design: ISSCC tutorial (162) and short-course (60) listings, forums and evening events, RFIC workshops; all have authors and abstracts on Xplore. Ask Yi whether the tutorials page should list them (2026-11-10).
- CICC 2020 invited tutorial 9075916 ("Digital Correction of DAC Nonlinearity...: Invited tutorial") is still missing: the CICC programme layer does not place it, and a CICC `--reparse` renumbers 2021-2023 (308 papers), so CICC was left as it was (2026-11-10).
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
