# ONGOING

Open threads, rewritten in place (`/Workflow:workspace-bootstrap`). A closed
thread moves to `DONE.md`. History is in git and `docs/07-history.md`.

## Thread: topic-survey literature reviews   (owner: sy-paper-log, updated 2026-11-04)
Status: qubit-rw Low and Mid (8 figures), mini-radio paper list, Low and Mid (8 figures) published to the site and iCloud; mini-radio Mid rows sol-checked (141 facts, 5 FIX + 1 by hand, applied; review-check 0/0).
Done when: the qubit Mid rows are checked and fixes applied, and Yi's optional PDFs (if any) are added as rows.
Next: on the qubit row check's reply, apply FIXes to `surveys/qubit-rw/work/mid_rows.tsv` and `out/review-mid.md`, then `review-check` and `review-html qubit-rw --level mid`.
Running: Mac Codex sol qubit row check (bg by9mnis6u) → Mac `~/lit-review/qubit-rw/row_check.tsv` · sy-mac-agent watcher: Mac `~/incoming_lit/*.pdf` → `k03:~/incoming_lit/` (until about 02:40).
Blocked: Codex on this PC runs as `codexsandboxoffline` (no network, no ssh config), so pool readers run as Codex on the Mac.
Pointers: `scratch/_resume-reviews.md`, `surveys/README.md`, `/Paper:lit-review`.

## Backlog
- Session-contents findings: 28 open from `tools/audit_session_contents.py` (parked 2026-11-04; `scratch/parked-threads.md`).
- Session decisions for Yi: 5 yes/no items (RFIC 2006 placement, CICC 2018 drops, `_print_order`, A-SSCC calls, A-SSCC 2020 cross-listing) (parked; `scratch/parked-threads.md`).
- Session known gaps: ESSCIRC 2005 programme, in-session order, A-SSCC 2024 codes, unchecked parser years, `# [c]` review (parked; `scratch/parked-threads.md`).
- VLSI 2024/2026 papers the saved programme drops (20 + 5), awaiting Yi's decision (parked; `scratch/parked-threads.md`).
- Cosmetic viewer items: orphaned SSCL Early Access page, its header text, master-index dark mode (parked; `scratch/parked-threads.md`).
- Yi reviews the `# [c]` code from the abstract and pacing work: `textclean.py`, `utils.py`, `config.py`, `scraper.py`, `tools/restore_abstracts.py`, `tools/repair_abstract_markup.py`, `html_builder.py` (surveys index), and the survey review code in `surveys/survey.py`.
- 14 abstracts the 2026-11-01 restore could not fetch (4,717/4,731); re-run `tools/restore_abstracts.py` some day, it picks up only those.
- Check the search page's default columns and widths on the wide monitor (`COLUMNS` in `search.html.j2`).
