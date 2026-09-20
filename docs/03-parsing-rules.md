# 03 — Parsing rules

> **Review status:** ⏳ Unreviewed *(default; update when Yi reviews)*
>
> ✍️ Claude-authored (2026-09-20).

How raw API records become papers, and exactly where that is unreliable.
All of this lives in `parser.py`.

## 1. Front-matter filtering

The API returns covers, tables of contents, author indexes, committee lists,
journal mastheads and advertisements as ordinary records, indistinguishable
from papers by metadata.

**Detection is title-only, by necessity.** `articleContentType`,
`displayContentType` and `contentType` are useless for this: every record in
RFIC 2024 — cover page, TOC, author index and real papers alike — reports
`"Conference Paper"` (verified 2026-09-20 against the live API).

Three rule sets, checked in order by `_is_front_matter`:

| Rule set | Match | Example caught |
|---|---|---|
| `SKIP_TITLES` | Whole title, lowercased | `"table of contents"`, `"committees"`, `"blank page"` |
| `SKIP_PREFIXES` | Title starts with | `"tutorial:"`, `"[front"`, `"timetable"` |
| `SKIP_PATTERNS` | Regex search | mastheads, `<ACRONYM> <YEAR> <front-matter noun>`, bracketed front matter |

### Design constraints

These rules run for **every** source, so they must be generic. Two failure
modes were designed against:

- **Too narrow.** The original rules hardcoded `^isscc\s+\d{4}` and similar,
  so RFIC/CICC/journal front matter passed straight through. The acronym is
  now a wildcard: `^[a-z][a-z\-.]{1,12}\s+\d{4}\s+(?:cover|toc|author index|…)$`
  catches `"RFIC 2024 Cover Page"` without naming RFIC.
- **Too broad.** Matching bare `"copyright"` anywhere would delete the real
  paper *"Watermarking-based copyright protection of sequential functions"*.
  Boilerplate words are therefore keyword-gated — `copyright (form|page|notice|transfer)`,
  `glossary$`, `^welcome\b` — rather than matched loose.

The same applies to bracketed titles: `[Blank page]` is front matter, but
`[Authors' reply to comments on "CMOS low-noise amplifier design"]` is a real
scholarly item. The bracket rule lists the front-matter keywords explicitly.

**Never add a bare substring to these lists.** Anchor it, or gate it on a
second keyword, and re-run the regression sweep in
`../scratch/2026-09-20-front-matter-audit.md` before committing.

### Session headers are never front matter

`"ISSCC 2024 Session 1 Overview: Plenary"` must survive filtering. The
acronym-prefix pattern deliberately excludes `Session N …` from its noun
list, and the unit tests in the scratch note cover it.

## 2. Session detection

Two regexes, tried in this order:

| Regex | Shape | Used by |
|---|---|---|
| `CICC_SESSION_TRAILER_RE` | `"Advanced MOSFET modeling - Session 2"` | CICC, older years |
| `SESSION_HEADER_RE` | `"[ISSCC 2024] Session 3 Overview: Wearables"` | ISSCC |

**Only ISSCC actually publishes session headers through the API.** This is a
property of the data, not a parser limitation:

| Source | Session data in the API | Result |
|---|---|---|
| ISSCC | Explicit `Session N Overview:` records | Real named sessions |
| RFIC | None — sessions exist only in the printed programme | One `"General"` session |
| VLSI | None | One `"General"` session |
| CICC | Each session opens with an untitled invited talk, not machine-distinguishable from a paper | One `"General"` session |
| Journals | Grouped by volume/issue instead | `"Vol. 61, Issue 3"` |

A single `"General"` session for RFIC/VLSI/CICC is the honest outcome. Do not
"fix" it by guessing session boundaries from page numbers or topic shifts —
that invents structure the source does not have.

### Record ordering

`_choose_conference_record_order` picks between the API's own order and a
`startPage` sort. Original order is trusted only when headers are numerous
(≥8 distinct), start early, spread across the year, and increase
monotonically; otherwise records are sorted by page. Some years return all
session headers bunched at the end, which only the page sort untangles.

## 3. Paper numbering

The canonical `paper_number` is **always** inferred as
`"{session}.{index_within_session}"`, starting at 1. A number printed in the
title is kept separately as `displayed_paper_number`, and a disagreement is
logged, not resolved. This keeps numbering contiguous even when IEEE's own
printed numbers skip or repeat.

### The prefix trap

A title prefix like `"14.2 A 28nm …"` is also used as a hint about which
session a paper belongs to, for years where record order is imperfect.

That hint fires only when the year contains **at least one real session
header**. Without that guard, VLSI 2024's

> `"122.7 TOPS/W Stdcell-Based DNN Accelerator Based on Transition Density"`

was read as paper 7 of session 122 — `122.7 TOPS/W` is a performance figure,
not a paper number. The parser created session 122, and because it was then
the only session, all 249 papers of the year were swallowed into it.
VLSI has no session headers at all, so the guard now suppresses the hint
entirely for that source.

## 4. Journal issue grouping

Journals set `group_by_issue=True` and group by `(volume, issue, isNumber)`:

- `volume` and `issue` present -> `"Vol. 61, Issue 3"`
- `volume` only -> `"Vol. 9"` (SSCL publishes continuously, with no issue
  numbers — every 2026 record carries `issue: null`)
- Early Access (`volume == "PP"`, `issue == 99`, or `isEarlyAccess`) is pulled
  out into a separate `early_access.json` shared across years, and rendered as
  its own page.

Early Access merges per year on write: scraping a single year must not drop
the other years' entries.

## 5. Known limits

- Affiliations are absent until `--enrich-affiliations` has run for that year.
- `conference_name` on a paper comes from `publicationTitle` and does not
  reliably distinguish merged VLSI tracks; the publication number does.
- Pre-2003 proceedings sometimes lack abstracts entirely; those papers are
  kept, and the gap is counted in `validation_summary.csv`.
