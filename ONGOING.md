# ONGOING

Open threads, rewritten in place (`/Workflow:workspace-bootstrap`). A closed
thread moves to `DONE.md`. History is in git and `docs/07-history.md`.

## Thread: session-contents findings   (owner: Claude, updated 2026-09-21)
Status: 28 findings open from `tools/audit_session_contents.py`: 26 session-code gaps and 2 keynote sessions holding technical papers.
Done when: each finding is fixed by an override or marked legitimate.
Next: decide whether to fetch the 8 uncached programmes (ISSCC 2006, CICC 2021-2026, VLSI 2020), then read the gaps.
Pointers: `scratch/_agent-out-session-contents.md`, docs/06.

## Thread: sessions, decisions for Yi   (owner: Claude, updated 2026-10-12)
Status: every conference-year but ESSCIRC 2005 has real sessions; these need a yes or no.
Done when: each item is answered and applied.
- [ ] RFIC 2006 1651130 (Garg): place it in RMO3C, where IEEE's numbering puts it?
- [ ] CICC 2018 8357100-8357102: these are CICC 2017 papers re-indexed under 2018. `__DROP__` them?
- [ ] `_print_order` re-ordered 27 reviewed years (552 papers moved within sessions, none changed session); CICC poster sessions now sit mid-year. Is that OK?
- [ ] A-SSCC calls: 2024 "Plenary" inferred; 2023 10347947 placed in Plenary 2 on the speaker; P1-P4 codes; 2016 Title Case; ESSCIRC 2004 `K`; RFIC 2001 capitals.
- [ ] A-SSCC 2020: 21 of 62 papers live under SSCL 2020. Cross-list them?
Pointers: docs/06, docs/07 §2 (2026-10-12 entries).

## Thread: sessions, known gaps   (owner: Claude, updated 2026-10-12)
Status: known, not fixed.
Done when: each item is fixed or moved to Backlog.
- [ ] ESSCIRC 2005 needs its programme from outside Xplore (Grenoble, 12-16 Sept 2005); a URL makes it a `data/programmes.tsv` line.
- [ ] Order inside a session is wrong where IEEE's start page is: A-SSCC 2010/2015/2021, RFIC 2006 (none usable), A-SSCC 2018 (4), 2011 (6123603), RFIC 2002 (1012027). Needs overrides that carry a printed position.
- [ ] A-SSCC 2024 sessions show in fetch order; plenary and industry codes differ by year.
- [ ] Only A-SSCC is checked paper by paper; the other conferences' parser-recovered years are not.
- [ ] Yi reviews the `# [c]` markers in `toc_sessions.py`, `session_overrides.py`, `parser.py`, `scraper.py`, `config.py`, `main.py`.

## Thread: VLSI papers the saved programme drops   (owner: Claude, updated 2026-10-05)
Status: a re-scrape drops 20 (2024) and 5 (2026) Circuits-looking papers that are absent from the saved programme; nothing changed yet.
Done when: Yi decides, and they are added by override or programme, not by loosening `drop_unknown`.
Next: Yi's decision. For 2026, 136 + 5 = 141 matches the count `vlsi_tracks.py` documents.

## Thread: cosmetic viewer items   (owner: Claude, updated 2026-09-21)
Status: open, low priority; evidence in `scratch/_agent-out-htmlreview.md`.
- [ ] `site/sscl/early_access.html` is orphaned (not linked from its index).
- [ ] Early Access pages show "Session Year 2026" and a stray leading " · ".
- [ ] The master `site/index.html` has no dark mode; the active density button fails contrast in dark mode (~2.14:1).

## Backlog
- Yi reviews the `# [c]` code from the abstract and pacing work: `textclean.py`, `utils.py`, `config.py`, `scraper.py`, `tools/restore_abstracts.py`, `tools/repair_abstract_markup.py`, `html_builder.py` (surveys index).
- 14 abstracts the 2026-11-01 restore could not fetch (4,717/4,731); re-run `tools/restore_abstracts.py` some day, it picks up only those.
- Check the search page's default columns and widths on the wide monitor (`COLUMNS` in `search.html.j2`).
