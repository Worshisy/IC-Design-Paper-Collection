# 07 - History: gotcha stories and handoff log

> **Review status:** ⏳ Unreviewed *(default; update when Yi reviews)*
>
> ✍️ Claude-authored. Moved verbatim from `AGENTS.md` sections 4 and 6 on
> 2026-11-02, when `AGENTS.md` was cut to rules, state and one-line pitfalls
> (the `/Workflow:workspace-bootstrap` layout). Numbers below are as measured
> on the dates given; re-measure before quoting them.

`AGENTS.md` keeps each gotcha as one line with its number; the story behind it
is here under the same number. Closed work is indexed in `../DONE.md`.

## 1. Gotchas, full text

- **Console encoding.** Python's stdout on this PC defaults to **GBK**; any
  script printing a paper title dies with `UnicodeEncodeError`. Always set
  `PYTHONIOENCODING=utf-8` (`update.bat` does). Mojibake seen in a terminal is
  a console artifact — the stored JSON is clean UTF-8.
- **`select_autoescape(["html"])` does nothing** for `*.html.j2` templates: it
  matches the *final* extension only. Autoescape was silently off for the
  life of the project. It is now `("html", "xml", "j2")`.
- **The search API has no affiliations.** `POST /rest/search` returns author
  names and IDs only. Affiliations need `GET /rest/document/<articleNumber>/authors`,
  one request per paper (~0.7 s). Hence the resumable
  `--enrich-affiliations` pass and `cache/<id>/affiliations.json`.
- **`articleContentType` cannot identify front matter.** Every RFIC 2024
  record — cover page, TOC and real papers alike — reports
  `"Conference Paper"`. Front matter can only be detected from the title.
- **RFIC and VLSI have no session data at all** in the API; a single "General"
  session is the honest result, not a bug. CICC opens each session with an
  untitled invited talk, which is not machine-distinguishable from a paper.
  Only ISSCC exposes real `Session N Overview:` headers.
- **A performance figure can look like a paper number.** VLSI 2024's
  `"122.7 TOPS/W Stdcell-Based DNN Accelerator"` created session 122. Prefix
  inference now requires the year to contain at least one real session header.
- **Journal Early Access is shared across years.** Scraping one year used to
  rewrite the whole `early_access.json`; it now merges per year.
- **Re-parse, do not re-scrape, after a parser change.** Raw records are
  cached in `cache/<id>/records/`; `main.py --conference all --reparse`
  rebuilds every year offline in seconds. A full re-scrape is ~27 minutes and
  several thousand requests at IEEE.
- **IEEE front matter is best identified by its abstract**, not its title.
  Covers, indexes and committee pages carry fixed boilerplate
  ("Presents the title page of the proceedings record."). 445 such records
  carry no title clue at all.
- **Old records carry pre-Unicode markup**: `/spl mu/`, `/sup 2/`, and
  undecoded HTML entities — 11.5k occurrences. `textclean.py` handles them.
  Leave unknown `/spl …/` names alone rather than guessing.
- **A search term is not a conference name.** CICC 2010 is indexed as
  "IEEE Custom Integrated Circuits Conference 2010" and searching "CICC"
  never found it, so the year was silently absent with no error file. When a
  year is missing, check discovery before assuming IEEE lacks the data.
  CICC 2016 really is absent from IEEE Xplore.

### Added 2026-09-21

12. **`--reparse` used to throw away every programme pass.** A rebuild from raw
    records carries no session structure. `reparse_year` now restores the saved
    layout by article number, re-drops papers a circuits-only programme had
    excluded, **and restores that year's affiliations from cache**. The
    affiliation restore lived only in `reparse_all`, so every per-year re-parse
    silently zeroed them — journals read 9,224 → 0 before this was caught.
13. **Re-running a healthy year could make it worse.** `enrich_sessions_from_toc`
    now scores the grouping a year already has and refuses any programme that
    does not beat it. ISSCC derives sessions from its own records; re-deriving
    2002 from the printed programme turned 26 sessions into 16.
14. **Never trust a front-matter rule without measuring it first.** Three
    plausible rules were tried and rejected on evidence this session:
    `"summary form only given"` would have deleted **34 real papers** (it is
    standard IEEE boilerplate on digest papers); IEEE's `ephemera` flag would
    have deleted **762**, mostly guest editorials and corrections that Yi chose
    to keep; a shared-word session check produced 1,047 findings, nearly all
    noise. **Always run the relevant audit and read the longest titles it would
    remove** — a real paper has a long technical title, so sorting by length
    surfaces false positives immediately.
15. **Heredocs mangle regex escapes.** Building a patch inside a bash heredoc
    turned `\b` into a literal backspace byte (0x08) in `toc_sessions.py`,
    silently disabling the index-exclusion filter for its whole life. Write
    patch scripts to a file and run the file.
16. **A hand-written list cannot report its own decay.** `esserc_tracks.py`
    held an entry normalising to 10 characters, below the 12-character floor
    the matcher requires, so it matched nothing for its entire existence. Every
    curated list now has an audit tool; run it after every edit.

### Added 2026-10-05

17. **A year file must be written exactly once, and that write owns the whole
    curated layer.** `scrape_year()` wrote a year file straight from raw API
    records - no session layout, no track split, no overrides, no affiliations
    - while `reparse_year()` applied all four. A refresh therefore flattened
    every year it touched: CICC 2024 went 25 sessions to 1, VLSI 2025 went 33
    sessions / 146 papers to 6 / 269 with the Technology track back in. Both
    writers now apply the layer.
18. **Re-applying it after the scrape cannot work.** The first attempt at 17
    re-parsed each year once the scrape had finished. `_restore_session_layout`
    reads the saved layout out of the year file, and the scrape had already
    overwritten it - there was nothing left to restore from. It has to happen
    inside `scrape_year`, after the records are parsed and **before** the file
    is written, the one moment both exist.
19. **Test the sequence, not the step.** The fix in 18 was checked by running
    the re-parse on its own and diffing all 259 year files: 0 changes, which
    proved nothing, because no scrape had run in between. A step that is
    idempotent in isolation can still be fatal in the real order. The backup
    taken beforehand (`output/*/json`) is the only reason this was a detour.
20. **Journal year files were written twice.** `scrape_year_range()` re-saved
    the dict `scrape_year()` had returned, to strip the Early Access issue out
    of it - after `scrape_year` had written the file and restored affiliations
    into it. The second write put the stale dict back, blanking affiliations
    for every journal year that had Early Access papers (1,620 for TCAS-II
    alone) and leaving the rest untouched, which made it look selective. The
    Early Access split now happens inside `scrape_year`, before its single
    write.
21. **A refresh must keep papers the saved programme has never seen.**
    `_restore_session_layout` drops anything absent from the saved layout,
    which is right for a re-parse (the other track's papers coming back) and
    wrong for a scrape (a paper IEEE published last week). `keep_articles`
    carries the difference: article numbers in the fetched records that were
    not in the raw record cache before the fetch.

### Added 2026-10-12

22. **A new source's acronym does not necessarily find all of its years.**
    An Xplore search for `"A-SSCC"` returns nothing for 2005, 2007, 2010 or
    2011, and `"ASSCC"` nothing from 2021 on; only the spelled-out name finds
    all 21. Probe every year of a new source's range before trusting one
    search term - a year that discovery misses is simply absent, with no
    error anywhere.
23. **Two sources can claim the same publication title.** A-SSCC's title
    contains "solid state circuits conference", which is ISSCC's entire
    `title_contains`, so ISSCC's matcher accepted A-SSCC publications. It had
    never been handed one, but one record in a different order would have
    scraped the wrong conference into ISSCC. Adding a source means re-reading
    the title rules of the sources it resembles; ISSCC now carries
    `title_excludes_any`.
24. **Judging a year's programme by one or two years is not judging it.**
    A-SSCC 2024 has no programme document and 2023's matched 0% of papers,
    from which this agent concluded the source had no usable programme. The
    full 21-year sweep recovered **11 years** - 193 real sessions. Run the
    sweep before writing the conclusion down.

25. **A programme can be filed under a title that says "cover".** A-SSCC
    2025 ships four records called "A-SSCC 2025 Cover Page"; three are
    covers, the fourth (article 11349376) is the whole 30-page programme.
    Candidate ranking is by page span, and `_page_value` could read decimal
    and roman pages but not the cover section's "c1".."c30", so the span
    read 0 and the document was never a candidate. Yi found it by looking at
    the Xplore listing. When a year has "no programme document", read that
    year's front-matter records with their page ranges before believing it.

26. **A programme that will not extract can still be read.** A-SSCC 2018
    is a scan (0 characters on 12 of 13 pages) and 2019 extracts with its
    columns decoupled; both had been written off as needing OCR or as too
    noisy. Rendered to PNG and read as images, they gave 90 of 90 and 88 of
    88 papers. Yi pointed this out by sending a screenshot of the page.
27. **`str.splitlines()` breaks on U+001C.** A-SSCC 2014's titles are in a
    font 29 codepoints below ASCII, where the digit 9 lands on U+001C - a
    line separator to Python. Every 9 silently cut its line in two (page 93
    became a "3" on its own line). Decode before splitting.
28. **IEEE's own `startPage` can be wrong.** Four A-SSCC 2018 papers are
    stored with start page "1" against printed 95, 143, 145, 149. Join on
    title *and* page, and treat a disagreement as something to read.
29. **Parallel agents need separate scratch folders and patch discipline.**
    Seven agents edited `toc_sessions.py` in one evening. What held: every
    patch asserted its anchor matched exactly once, and each took its
    "before" from the live file with only its own block stripped. What did
    not: a shared scratchpad, where two agents overwrote each other's
    `sweep.py`. Give each its own folder.
30. **Recovering a year can raise the unassigned count.** A flat year has no
    unassigned papers by construction. A-SSCC went 102 -> 143 while going
    from 12 recovered years to 21.

31. **A year the parser recovered is not a year that has been checked.**
    Eight A-SSCC years counted as recovered held 183 papers in the wrong
    session - none unassigned, so no count showed them. Plenary and industry
    sections print no session number and fall into the first technical
    session; `I1-1` reads as `11-1`; two headers to a page lose one. Join
    every stored paper to a printed entry and compare per-session counts.
    See `docs/06-session-recovery.md`. Only A-SSCC has had this done.
32. **`apply_overrides` used to append.** A moved paper went to the end of its
    session and a new session to the front of the year, for every override
    since September - 782 papers and 37 years across all six
    conferences. `_print_order` now places them, and only them. It was
    measured by re-applying all 101 curated years and comparing with a
    backup: 0 papers changed session.
33. **A sub-agent that finds its brief too narrow should say so, not widen
    it.** The agent placing 2010's stragglers saw that session 1 held 13
    papers against a printed 6, reported it, and left it. That report is why
    2009 and 2021 then got a full check; 2009 had ten more.

### Added 2026-10-27

34. **The search API truncates abstracts.** `/rest/search` cuts every
    abstract at about 400 characters: 56,255 of 61,585 stored abstracts were
    395-410 long. Searches over "title + abstract" only ever saw the first
    400 characters. The full text is one request per paper to
    `/rest/document/<articleNumber>/abstract` (checked: 1,688 characters
    against the search's 403 for the same paper, matching OpenAlex).
    `tools/restore_abstracts.py` fetches them into
    `cache/<id>/abstracts_full.json`, and `Scraper._restore_full_abstracts`
    re-applies that cache before every year-file write, so refreshes and
    re-parses keep the full text (checked on SSCL 2026: 403 -> 1,157 and 985
    after a re-parse).
35. **The full-abstract endpoint returns JATS/MathML markup with attributes**
    (`<sup xmlns:mml="...">2</sup>`, `<inline-formula><tex-math>$N$</tex-math>`,
    `<tex>`, `<para>`, `<xref>`, `<etal/>`). `clean_text` only knew bare tags,
    so it dropped `</sup>` and left the opening tag: 17,974 abstracts showed
    raw tags (Yi spotted it on 2026-11-02). `textclean._strip_markup` now
    handles them, including the damaged form; formulas become `$...$` for
    MathJax. Only listed tag names are touched, because abstracts contain real
    "<" ("BER<10^-12"). `tools/repair_abstract_markup.py` re-cleans stored text.

### Added 2026-11-10

37. **A front-matter title rule deleted 31 real tutorial papers.** `SKIP_PATTERNS`
    had `\btutorials?$` for programme entries ("Tutorials", "ISSCC 2024
    Tutorials"), with no check of the record, so every journal paper titled
    "...: A Tutorial" or "...—A Tutorial" was dropped: TCAS-II 21, TCAS-I 6,
    TMTT 2, JSSC 1, CICC 1 (e.g. JSSC 2000 "Oscillator phase noise: a
    tutorial"). Titles ending "A Tutorial Brief" or "Review" survived, which hid
    it. Found when Yi asked about TCAS-II 2024 p. 1663 (Xplore 10342829); TCAS-II
    2024 then held 1,054 fetched records but 1,000 saved (46 front matter, 1
    Early Access, 7 tutorials). Fix: `_is_tutorial_paper` lets a record with
    authors and an abstract over 150 characters pass that one rule; the
    tutorial-presentation abstracts are still caught by the abstract rules.
    Dry run over every cached record: exactly the 31 change; 25 programme
    listings stay out. A `--reparse` of the four journals added 30 (the CICC
    2020 invited tutorial did not come back through the programme layer, and
    the CICC reparse renumbered 308 papers of 2021-2023, so CICC was restored
    from the backup). Journal paper numbers shift by position within the issue
    that gained a tutorial (522 papers); nothing else changed. Abstracts and 12
    affiliations of the restored papers were fetched through the Mac (Yi's
    route for that task).
    Yi then asked whether reviews were covered too. A scan of every cached record
    with authors and an abstract that the parser still drops (503) found three
    more journal papers behind other programme rules: "50 Years of CORDIC"
    (TCAS-I 2009), "50 years of RF and microwave sampling" and the MTT-S
    50-year history (TMTT 2002/2003) behind `^\d{1,3}\s+years\s+of\b`, and a
    TCAS-II 2021 "Tutorial: Design of ..." behind the `tutorial:` prefix and the
    programme pattern. The exception now also excuses those rules for journal
    records (`articleContentType == "Journals"`); a second reparse of TCAS-I,
    TCAS-II and TMTT added exactly these 4. The rest of the 499 are editorials,
    editor messages, special-issue introductions, and conference programme items
    (ISSCC tutorial and short-course listings, forums, evening events, RFIC
    workshops) that stay out of the log by design. The audit's `RECORD_CASES`
    were never run until then; running them shows one old failure
    ("Plenary Speaker 1: ...", not filtered), left for Yi.

---

## 2. Handoff log

### 2026-10-22 — citation counts (Claude)

Yi asked for each paper's citation count, sortable in search, and easy to
update. IEEE's search API already returns `citationCount` per record, so this
needed no new endpoint: `Paper.citation_count` (parser reads it), a "Cited"
column and **Sort → Citations** in `search.html` (index field `k`), the count
under the paper number on year pages, and `tools/refresh_citations.py`, also
run by `update.bat --citations`. The tool patches year files in place and
does not re-parse, so the curated layer cannot move.

Measured: first pass from the record cache, then a live pass, 866 search pages
in 0:29:45, no failures. All 62,007 papers carry a count; 4,607 are 0.
Against a backup of `output/` taken first, all 600 JSON files are identical
apart from `citation_count`. A re-parse of A-SSCC 2020, ISSCC 2024 and JSSC
2023 reproduced the counts; ISSCC 2024's re-parse also rewrote
`proceedings_url` (a pre-existing difference between scrape and re-parse),
so that file was put back.

One slip against hard rule 3: the site was synced to iCloud after the offline
pass (309.6 MB) as well as after the live one (237.9 MB). Use `--no-sync`
until the last step.

### 2026-10-12 — A-SSCC added as the 11th source (Claude)

Yi asked for A-SSCC. `config.py` gained an `asscc` entry (three search terms,
`first_year` 2005), ISSCC gained `title_excludes_any` so the two cannot
collide, and `parser.py` gained four rules for A-SSCC's programme items
(advance programme, floor plans, site map, `PD-n:` panel codes, the
`A-SSCC <year> Preface/Forward/program` prefix, and the proceedings record
itself).

Measured before applying those rules, over all 62,439 stored papers: the only
false positive was TCAS-II 2020's "... With a Common-Centroid Floorplan", a
real paper. Floor plans therefore went into `PROGRAMME_TITLE_RE`, which only
fires on authorless records, not into the title rules.
`tools/audit_front_matter.py` passes its 79 unit cases.

Result: 2,254 raw records -> 2,134 papers -> 2,118 after the new rules, all
with per-author affiliations, sessions for 11 of 21 years. One ISSCC record
("Special Event: Student Research Preview (SRP)") now matches a pre-existing
rule and will disappear the next time ISSCC is re-parsed.

**ESSCIRC has no 2020 and never will.** The 46th edition was cancelled for
COVID - 2019 is the 45th, 2021 the 47th - and an article search restricted
to 2020 returns zero records. Recorded in `docs/02-data-sources.md` so the
gap is not re-investigated.

### 2026-10-12 (night) — "fix all": every unassigned paper, every flat year (Claude)

Yi asked for everything outstanding to be fixed. Twenty Sonnet agents, one per
problem year, each working by curated override only (none could edit code),
all from one rulebook. Results:

- **A-SSCC**: 143 unassigned -> 0. Every year checked paper by paper against
  print, which found **183 papers in the wrong session** across eight years
  (gotcha 31). 48 damaged session names repaired in 2006, 2016 and 2021.
- **RFIC 2001, 2002, 2003, 2005, 2006**: flat -> 67, 115, 168, 161 and 129 of
  130 papers placed, read as page images. 2006 was never programme-less:
  IEEE titles its digest "Sessions".
- **ESSCIRC 2003, 2004**: flat -> 175 and 114 placed. **ESSCIRC 2005** stays
  flat; the only programme cached is ESSDERC's.

Code changes, both `# [c]`: `session_overrides._print_order` (gotcha 32), and
nothing else. It was applied by re-running `reparse_year` over all 101 years
that have overrides; against the backup, 0 papers changed session, 37 years
changed session order and 782 papers changed position within a session - 27
of those years and 552 of those papers in sources not otherwise touched today
(ISSCC 2000-2002, VLSI 2000-2003, CICC 2000-2008, ESSCIRC, RFIC 2000 and
2007). Every one read moved toward printed order, but they are years Yi had
reviewed, so they are listed in `ONGOING.md` to be looked at.

Calls made on Yi's behalf, all reversible by editing the override table:
A-SSCC 2016's names put in Title Case (printed in capitals); 2021's room code
("A2L-D") taken out of the session name, where the programme prints it in a
separate cell; plenary and industry codes left as each agent chose them
(`P1`, `PL-1`, `P-1`, `I1`, `Industry1`), so they differ by year.

Yi then ruled on items a conference ran but printed no session heading for:
group them plainly. A-SSCC 2006's four plenaries are now `PL` "Plenary" and
2008's two panels `PD` "Panel Discussion" - both confirmed by the print. 2024's
two single-speaker talks were given `PL` "Plenary" as well, **on the speaker
and abstract alone**: they are on none of the 29 programme pages, IEEE's
contents endpoint returns no heading for that issue, and the conference site
no longer serves a programme. That block says so in its comment line.

The backup of all six conferences' year files and of the override table from
before the clean-up is in the session scratchpad, `final_backup/`.

### 2026-10-12 (evening) — all 21 A-SSCC years recovered, by sub-agents (Claude)

Yi supplied the material year by year (Xplore links, a university-hosted PDF,
an epapers2.org page, two uploaded PDFs) and asked that each special case go
to its own sub-agent rather than be scripted in the main session. Ten Sonnet
agents ran, plus two reviewers. Per year:

| Year | Material | Result |
|---|---|---|
| 2025 | Xplore "Cover Page" 11349376 | 30 sessions, 1 unassigned |
| 2024 | epapers2.org, 29 session pages | 29 sessions, 2 unassigned |
| 2023 | Xplore "Advance Program" 10347954 + 11 overrides | 26 sessions, 0 unassigned |
| 2022 | Xplore "Advance Program" 9980671 | 21 sessions, 3 unassigned |
| 2020 | Xplore "Table of contents" 9336099 | 15 sessions, 5 unassigned |
| 2019 | 9056958, read as images, 88 overrides | 20 sessions, 0 unassigned |
| 2018 | 8579348, read as images, 90 overrides | 20 sessions, 0 unassigned |
| 2014 | 7008844, glyph-shifted titles | 21 sessions, 0 unassigned |
| 2013 | "[Front matter]" 6690966 | 20 sessions, 9 unassigned |
| 2007 | VDEC advance programme (not in Xplore) | 17 sessions, 22 unassigned |

`toc_sessions.py` gained rules for each printed shape (table in
`docs/06-session-recovery.md`), an `explicit_codes` flag that lets title
matching beat position matching when a paper's code names its session, and
`_unshift_title_lines()` for 2014. `scraper.py` gained a guard keeping
journals out of the programme pass: SSCL 2020-2026 are one volume group a
year, which `_lacks_sessions` read as a collapsed conference. It had never
fired - no journal has a cached programme - but `--conference all
--toc-sessions` would have tried.

Verified at the end against a snapshot of all 300 programme parses taken
before any of the day's edits: 6 changed, every one A-SSCC's, 294 identical,
ISSCC 2002 among them.

Judgment calls in the 2023 override block, for Yi to confirm: article
10347947 is stored as "5G Lessons Learned and an Outlook on 6G" but printed
as "Envisioning 6G Mobile New World" - placed in Plenary Speech 2 on the
speaker's name alone; and the plenary codes P1-P4 are not printed (plain 1-4
would collide with technical sessions 1-4). Today's code edits carry `# [c]`.

### 2026-10-12 (later) — A-SSCC 2025's programme, hidden as a cover page (Claude)

Yi sent the Xplore link for article 11349376 and a screenshot of four
identically titled "A-SSCC 2025 Cover Page" records, one of them 30 pages.
That record is the full programme. Three changes, each measured against all
300 cached programme PDFs before being applied (2 changed, both A-SSCC):

- `_page_value` now reads cover-section pagination ("c1".."c30"), so the
  document's span is no longer 0 and it enters the candidate ranking.
- `SPACED_SESSION_RE` for A-SSCC's separator-less headers ("Session 1
  Advanced System Integration Circuits"), accepted only when a `Chair:` line
  follows within three lines. Without that guard it also matched a schedule
  grid in 2022, a mangled 2023 extraction, and two junk headings in ISSCC
  2002 - a year already fixed and not to be regressed.
- `ASSCC_PAPER_RE` for papers coded "S-1-1(4319) Title", the session number
  inside the code and the title wrapping onto the next line.

One more fix fell out: the VLSI rule that re-reads a session's name from the
line below the header (VLSI heads sessions with a room) was taking A-SSCC's
"Chair:" line, naming all 30 sessions after their chairs. It now skips a
chair line.

Result: A-SSCC 2025 went from one unnamed group of 135 papers to **30 real
sessions, 134 papers placed, 1 unassigned**. The source now has 12 of 21
years with real sessions. 2013 still parses 21 session names but places
everything in one session, so the guard rejects it - open in `ONGOING.md`.

### 2026-09-20 — Claude
Audited the project (no git history existed; `git init` done, code-only
`.gitignore`). Ran every code path against the live API to confirm behaviour
before changing anything. Fixed: generic front-matter filtering, the VLSI
false-positive session, Early Access clobbering, Jinja autoescape, embedded
JSON escaping, ISSCC-hardcoded defaults, import-time directory side effects,
unused imports. Added: per-author affiliation fetching, the like/mark/note
system, a responsive non-truncating viewer, `update.bat` + `update_database.py`,
`serve.py`. Rewrote both page templates and extracted shared CSS/JS partials.
Full re-scrape of all 9 sources run afterwards.

A Sonnet style-review pass ran over the original code; its findings are
recorded in `scratch/2026-09-20-style-review.md` with what was and was not
acted on. Per-source title audits (one agent per source) are recorded in
`scratch/2026-09-20-source-audits.md`, including the heuristics that were
measured and **rejected** for producing false positives on real papers.

---

### 2026-09-21 — session recovery, track leaks, and the override table (Claude)

The day's theme: papers were present and clean, but **grouped wrongly**, and
several checks that looked right were deleting real work.

**Session structure.** Collapsed "General"-only conference years went **65 →
21**; unassigned papers **573 → 1**. Work split between parser rules (which
generalise) and a curated override table (for fixed past years no rule can
reach). New layouts recognised: RFIC coded sessions and its digit-less
Interactive Forum code, CICC en-dash headers and bare poster headings,
ESSCIRC dot-coded papers and code-prefixed headers, ISSCC overview-page
markers, and a repair for ESSCIRC PDFs whose font sits 29 codepoints below
ASCII. See `docs/06-session-recovery.md`.

**Root causes worth remembering**, each found by an agent and each explaining
many symptoms at once:

- `is_plausible_session_name` rejected any two-word Title Case name as a
  person's name, silently merging **35 real sessions** into whatever preceded
  them — and, through a whole-session track drop, **deleting 8 real circuits
  papers** from ESSERC 2024. It only ever correctly caught "Coffee Break".
- IEEE files the session chairs' introduction as a paper whose title is the
  session's own name; 90 such records were inflating sessions.
- CICC prints poster sessions as a bare unnumbered heading, so their papers
  were attributed to the preceding session — **327 of 683 override lines**
  traced to that one shape.

**Tooling.** Four audit tools now exist (`audit_front_matter`,
`audit_session_overrides`, `audit_session_contents`, `audit_device_tracks`).
`audit_session_contents.py` was written after Yi found three mm-wave radar
papers filed under a plenary keynote heading that every mechanical check had
passed; its strongest signal is a gap in the printed session codes.

**Affiliations** completed for the whole corpus: 18,610 journal papers and
11,755 conference papers, now 99.2% coverage. `tools/backfill_affiliations.py`
gained `--sources` so a session rebuild can own the other sources' year files
concurrently without the two clobbering each other.

**Process note for the next agent.** Every rule proposed this session was
measured against stored data *before* being applied, and three were rejected
for deleting real papers (see gotchas 14). Do the same: run the audit, sort
what it would remove by title length, and read the longest ones. A real paper
has a long technical title, so false positives surface immediately.
