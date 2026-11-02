# 06 — Session recovery and overrides

> **Review status:** ⏳ Unreviewed *(default; update when Yi reviews)*
>
> ✍️ Claude-authored (2026-09-21).

How a year's papers get grouped into the sessions the conference actually ran,
and what to do when no rule can manage it. Companion to
[`03-parsing-rules.md`](03-parsing-rules.md), which covers deciding whether a
record is a paper at all.

## Why this is hard

The search API returns a flat list of papers. It carries **no session
structure** for any source except CICC 2021+, which populates a `majorTopic`
field. Everything else has to be recovered from the **printed programme**,
which IEEE publishes as a front-matter PDF alongside the papers.

Those PDFs are not a clean data source. Across the corpus they arrive as:

- clean single-column text (most years since ~2010);
- OCR'd scans of print, with character errors (`Overview` → `Ouerview`, and
  `SESSION MON1A` → `MONlA`, which breaks any digit-matching rule);
- a font whose glyph codes sit a fixed 29 below the ASCII they print, so
  extraction yields `(66&,5&` for `ESSCIRC`;
- multi-column tables that `pypdf` reads **column-major**, detaching a paper's
  code from its title beyond repair by any regex.

## The pipeline

`scraper.Scraper.enrich_sessions_from_toc(year)` runs, in order:

1. **IEEE's TOC endpoint** — `fetch_major_topics()`. Authoritative where it
   exists, which measurement shows is CICC 2021 onward and nowhere else.
2. **The printed programme.** `find_toc_records()` ranks the year's
   front-matter records, `download_toc()` caches the PDF under
   `cache/<source>/toc/<year>-<article>.pdf`, `extract_text()` reads it
   (repairing the glyph shift on the way), and `parse_programme()` turns it
   into sessions, paper entries and page markers.
3. **`assign_sessions()`** maps the year's real papers onto that programme.

### Choosing between candidate documents

A year often ships several front-matter records — a two-page "Session List"
beside a thirty-page "Table of Contents". Every candidate is parsed, then each
is **trialled on a copy of the year** and scored by the grouping it actually
produces: papers placed, then named sessions. The best one wins.

This is not the obvious design and the obvious ones both failed:

- *first that applies* let a thin document win by being listed earlier and
  collapsed RFIC 2009 from 27 sessions to 2;
- *richest parse* let a document with more headings but worse title matching
  win, which regressed RFIC 2008 (0 → 12 unassigned) and 2014 (3 → 8).

A candidate is ranked by how many pages it spans, which means the span has
to be readable. A-SSCC 2025's programme is paginated "c1"-"c30" and titled
"A-SSCC 2025 Cover Page", identical to the three genuine covers it sits
beside; until `_page_value` learned cover-section pagination its span read 0
and it never entered the ranking at all. **A document's title is not what
makes it the programme - its length is.**

### Two guards that must stay

**Never worse.** The grouping a year already has is scored first, and a
programme is applied only if it beats it. ISSCC derives its sessions from the
records themselves, and re-deriving 2002 from the printed programme turned 26
sessions into 16 — re-running a healthy year must never cost it structure.
This is what makes the whole pipeline safe to re-run.

**No degenerate groupings.** A programme can clear the coverage floor while
dropping every paper into one or two buckets. ESSCIRC 2003 did exactly that:
58% of 175 papers into a single session, inventing a 74-paper Unassigned pile
that was worse than the single "General" session it replaced.

### Matching strategies

`assign_sessions()` tries three and keeps the best, then **fills the winner's
gaps from the other**, since page and title matching both key on the
programme's own session numbers:

| Strategy | How | Used when |
|---|---|---|
| page markers | the programme prints a page per session; papers fall in ranges | the programme has `Page N` or `Session Overview … <page>` lines |
| title match | a 40-character normalised prefix of the title | titles are printed cleanly |
| reading position | where a paper's title sits relative to headings in the raw text | there are no codes or page markers |

Title matching also has a **unique-short-prefix fallback**: a title shorter
than the PDF's wrap width runs on into the author line, so its 40-character key
carries author text the real title never has. A 25-character key is used when
it names exactly one session.

`normalise()` NFKC-folds before filtering. Dropping non-ASCII (the previous
behaviour) desynced it from the search haystack, which kept those characters —
one character out of step breaks every match crossing a `μ`, `Δ`, `Ω` or `²`,
and IEEE titles are full of them. NFKC also collapses MICRO SIGN U+00B5 against
GREEK SMALL LETTER MU U+03BC, which the API and the PDF disagree on.

## Programme layouts recognised

Each was added because a real year needed it; see `toc_sessions.py` for the
regex and the year that motivated it.

| Layout | Example | Source |
|---|---|---|
| numbered | `Session 12: High-Speed Wireline` | most |
| en dash | `Session 1 – Plenary Session` | CICC |
| coded | `Session RMO1B: Advances in LNA Design` + `RMO1B-1 8:00 AM` | RFIC |
| Interactive Forum | `Session RTUIF:` — a code with **no digit** | RFIC |
| dot-coded papers | `C01.01 - Title` | ESSCIRC 2002 |
| code-prefixed | `A3L-A  Analog Techniques` above a `Date:/Room:` block | ESSCIRC |
| bare + name below | `SESSION 5` then the name on a following line | VLSI, older ISSCC |
| poster | a bare `Poster Session` heading, papers `MP-01` / `M-1` / `P.16` | CICC |
| overview pages | `Session Overview and Abstracts 10` gives the start page | ISSCC 2000-2003 |
| dot leaders | `Title ....... 24` | several |
| no separator | `Session 1 Advanced System Integration Circuits` above a `Chair:` line | A-SSCC 2013, 2025 |
| session in the code | `S-1-1(4319) Title`, wrapping onto the next line | A-SSCC 2025 |
| advance programme | `Session Session 6: Name` + `6.1(7053) 10:50 - 11:15`, or a bare `14: Name` under a label block + `14-1   9:00~9:25` | A-SSCC 2022, 2023 |
| `Sn Session:` | `S2 Session: Name` above `Session date and time:` + `S2-1 (1118) 11:10-11:35` | A-SSCC 2020 |
| co-chairs line | `Session 1 Name`, a date line, `Session Co-Chairs:` + `1-1 13:45-14:10` | A-SSCC 2007 |
| web session page | `<Name> Session` / `Session Type:` / `Session Code: A1L-B`, then id, topic, title | A-SSCC 2024 (epapers2.org) |
| shifted title lines | titles 29 codepoints below ASCII beside plain names; shifted "9" is U+001C | A-SSCC 2014 |

When a paper's code names its session outright (`S-1-1`, `6.1`, `S2-1`), the
programme sets `explicit_codes` and title matching beats position matching.
Position is the wrong tool there: A-SSCC 2022 reprints every demo paper's
title in a second list outside its session, and position matching piled 23
papers into session 5.

## What is not a session name

`is_plausible_session_name()` rejects affiliations, country tails, and:

- **fillers** — "Coffee Break", "Welcome Reception". This replaced a
  "looks like Firstname Lastname" heuristic that matched ordinary two-word
  topics ("Power Converters", "Compact Modeling") and silently merged **35 real
  sessions** into whatever preceded them. It only ever caught "Coffee Break".
- **anything without a word** — `- 16:25`.
- **anything starting with a clock time** — `- 9:25 (Plenary)`. The word rule
  alone was not enough: 111 of VLSI 2017's 116 "sessions" held a single paper
  because each paper's printed time was being read as a heading.

## Session-overview records

IEEE files the session chairs' own introduction as if it were a paper. Its
title is the session's name differing only in case ("Radio receiver techniques"
against the session "Radio Receiver Techniques"), so
`drop_session_overview_records()` recognises it without reading the abstract.

The guard matters: a session that holds a single paper is sometimes *named
after that paper*. Requiring the matching session to hold at least two other
papers separates the cases — measured corpus-wide it spared exactly the real
papers and removed 90 overview records.

## Overrides — for what no rule can reach

A past conference year never changes, so once a paper's real session has been
read off the printed programme it is a fact, not a guess. Some years defeat
every rule: a column-major extraction, or a programme IEEE never published.

`data/session_overrides.tsv`, read by `session_overrides.py`:

```
conference <TAB> year <TAB> article_number <TAB> session_code <TAB> session_name
```

- Papers match on **article number**, stable in Xplore.
- `session_code` is what the proceedings printed (`C6L-4`, `RMO1B`, `12`); it
  becomes the page's session label and the prefix of its papers' numbers.
- Identical `session_name` spelling for every paper in a session, or they split.
- A `session_name` of `__DROP__` removes a record that is not a paper.
- The merge looks for a session with the same **code and name**, and falls
  back to the same **name alone**. The first rule exists for VLSI 2012, which
  names sessions after the room ("Coral Ballroom 4" appears more than once);
  the fallback means two *new* sessions cannot share a name even under
  different codes - A-SSCC 2013's two plenary sessions, both first written as
  "Plenary", collapsed into one until they were named apart.
- **Order.** A paper an override moves is placed by start page within its
  session, and a session made entirely of overridden papers is placed among
  the others - by its number when every session code in the year is a plain
  integer, otherwise by the middle of its page range. Nothing else moves, and
  where the evidence is poor nothing moves at all: a session whose pages are
  missing or repeated keeps its order (A-SSCC 2010 stores "1" for every paper;
  ISSCC 2002 interleaves two volumes), and a session scattered through the
  volume, such as invited papers, stays where it was. Before this, a moved
  paper landed at the end of its session and a new session at the front of
  the year: A-SSCC 2012 read "I2 1 3 P2 5 7 ... P1 I1 2 4 6".

Applied **after** parsing and after both track filters, at every pipeline entry
point, so an override survives a re-parse and an incremental update.

A programme that will not *extract* can still be *read*. A-SSCC 2018 is a
scan with no text layer on 12 of 13 pages; 2019 extracts with its code and
title columns decoupled. Both are perfectly legible as page images, so each
was rendered (`pdftoppm`; the Read tool rejects these PDFs as
password-protected) and transcribed into overrides - 90 and 88 papers, joined
on printed start page *and* title. No OCR dependency was needed.

Two traps from that work. IEEE's `startPage` is wrong for four 2018 papers
(stored "1", printed 95, 143, 145, 149), and since papers sort by start page
inside a session those four display first. And 2018's plenaries are paginated
separately as (1), (5), (9), (13), stored bare, colliding with papers 2-1 to
2-4 - a page-only join swaps keynotes with industry papers.

**Run `tools/audit_session_overrides.py` after editing.** It reports each entry
as in place, removed as intended, or stale — a hand-written list that stops
matching is otherwise indistinguishable from one that works.

## Auditing

| Tool | Answers |
|---|---|
| `tools/audit_front_matter.py` | is each record a paper? |
| `tools/audit_session_overrides.py` | does every override still match? |
| `tools/audit_session_contents.py` | do a session's papers belong under its name? |
| `tools/audit_device_tracks.py` | is the circuits/devices split complete and live? |

`audit_session_contents.py` exists because every other check passed a page
showing three mm-wave radar papers under "Plenary Keynote 1: José Epifânio da
Franca". Its strongest signal is a **gap in the printed session codes** — a
missing number means a session was never parsed, and its papers had to land
somewhere, usually the session before it.

A fourth check — "does any paper share a word with the session name" — was
built and removed. Singular against plural alone made it fire on correct
sessions ("IoT and Wireless Receivers" holding receiver papers): 1,047
findings, nearly all noise. A check that cries wolf is worse than no check.

## A year the parser recovered is not a year that has been checked

On 2026-10-12 every paper of every A-SSCC year was compared with its printed
programme. Eight years that had been counted as recovered held **183 papers
filed in the wrong session** - 2012 (58), 2005 (53), 2006 (22), 2017 (13),
2008 (11), 2009 (10), 2010 (10), 2011 (6). None was unassigned, so no count
had ever shown them. The causes, each seen more than once:

- **Sections with no session number.** Plenary talks and industry programmes
  print a heading but no "Session N", so their papers fall into the first
  technical session. A-SSCC 2008's first ADC session held 17 papers; the
  programme prints 7.
- **A code read as a number.** `I1-1` (capital I, Industry) read as `11-1`.
- **Two sessions to a page**, with only one of the two headers kept: 2012
  lost every odd-numbered session.
- **A header the text layer puts in the wrong place**, so a session's papers
  slide into its neighbour (2017's sessions 5-7 and 17-19).
- **Everything after the last numbered header** - posters, a design contest -
  absorbed by the last session (2005's session 12 held 59 papers, not 6).

`tools/audit_session_contents.py` flagged three of the eight. The reliable
check is the dull one: join every stored paper to a printed entry, and compare
each session's stored count with its printed count.

Only A-SSCC has had this done. The other conferences' parser-recovered years
have not.

## Known limits

- **ESSCIRC 2005 is the one conference-year still a single group.** Its cached
  "programme" is ESSDERC's - the co-located device conference - and points to
  a separate ESSCIRC booklet that Xplore never indexed. It needs a programme
  from outside Xplore, as A-SSCC 2007 and 2024 did.
- **13 years have no programme in Xplore**: RFIC 2019; CICC 2000, 2001, 2005,
  2019, 2020; ESSCIRC 2005; VLSI 2005, 2014, 2016, 2018, 2024, 2026. All but
  ESSCIRC 2005 have sessions from another source. RFIC 2006 was on this list
  in error: IEEE files its whole digest under the title "Sessions".
- **The six years `pypdf` reads column-major** - RFIC 2001, 2002, 2003, 2005;
  ESSCIRC 2003, 2004 - were read as page images on 2026-10-12 and are fully
  placed. No layout-aware extractor was needed.
- **IEEE's start pages are unusable for whole years**, which leaves papers in
  those years out of printed order inside a session: A-SSCC 2010, 2015 and
  2021 store "1" for every paper, RFIC 2006 stores "4 pp.". Single wrong
  values: four in A-SSCC 2018, one in 2011, RFIC 2002's "186A".
- **4 papers are unplaced**, listed in `ONGOING.md`.
