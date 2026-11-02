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

**The API's own type fields cannot help.** `articleContentType`,
`displayContentType` and `contentType` are useless here: every record in
RFIC 2024 — cover page, TOC, author index and real papers alike — reports
`"Conference Paper"` (verified 2026-09-20 against the live API). Detection
therefore works from the title and the abstract.

Four signals, checked in order. The first three are title-only
(`_is_front_matter`); the fourth needs the record (`_is_front_matter_record`):

| Rule set | Match | Example caught |
|---|---|---|
| `SKIP_TITLES` | Whole title, lowercased | `"table of contents"`, `"committees"`, `"blank page"` |
| `SKIP_PREFIXES` | Title starts with | `"tutorial:"`, `"[front"`, `"timetable"` |
| `SKIP_PATTERNS` | Regex search | mastheads, `<ACRONYM> <YEAR> <front-matter noun>`, bracketed front matter, forums/panels/evening events, venue maps, committee listings, catalogue entries |
| `FRONT_MATTER_ABSTRACTS` | Abstract prefix | IEEE's fixed boilerplate: *"Presents the title page of the proceedings record."*, *"The author index contains an entry for each author…"*, *"This page or pages intended for user notes."* |

### The abstract signal is the strongest one

IEEE attaches fixed boilerplate abstracts to front matter, which identifies
covers, indexes, committee pages and author-instruction pages **whatever the
title says** — 445 records that no title rule would catch.

One guard: the auto-generated *"The following topics are dealt with: …"*
abstract marks front matter almost always, but one real paper (a 2018 CICC
terahertz radio) carries it too. That pattern therefore only applies to short
titles, since the real paper's title is long.

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
second keyword, and run `tools/audit_front_matter.py` before committing —
75 unit cases plus a sweep that prints the longest removed titles, which is
where false positives hide. Add a unit case for whatever prompted the change.

### Session headers are never front matter

`"ISSCC 2024 Session 1 Overview: Plenary"` must survive filtering. The
acronym-prefix pattern deliberately excludes `Session N …` from its noun
list, and `tools/audit_front_matter.py` covers it as a unit case.

## 2. Session detection

Three regexes, tried in this order:

| Regex | Shape | Used by |
|---|---|---|
| `CICC_SESSION_TRAILER_RE` | `"Advanced MOSFET modeling - Session 2"` | CICC, older years |
| `SESSION_HEADER_RE` | `"[ISSCC 2024] Session 3 Overview: Wearables"` | ISSCC |
| `ALPHA_SESSION_HEADER_RE` | `"Session MO1A: Integrated Mixers I"` | RFIC 2004 |

The alphanumeric form matters because `SESSION_HEADER_RE` requires digits
after "Session"; RFIC 2004's codes (`MO1A`, `M02B`, `TUIFR`) are alphanumeric,
so its 25 session rows were previously counted as papers. Such a session keeps
its printed code in `session_code` and gets the next free sequential number.

**Only ISSCC actually publishes session headers through the API.** This is a
property of the data, not a parser limitation:

| Source | Session data in the API | Result |
|---|---|---|
| ISSCC | Explicit `Session N Overview:` records | Real named sessions |
| RFIC | None — sessions exist only in the printed programme | One `"General"` session |
| VLSI | None | One `"General"` session |
| A-SSCC | None | One `"General"` session, until the printed programme is read: that recovers all 21 years |
| CICC | Each session opens with an untitled invited talk, not machine-distinguishable from a paper | One `"General"` session |
| Journals | Grouped by volume/issue instead | `"Vol. 61, Issue 3"` |

A single `"General"` session for RFIC/VLSI/CICC/A-SSCC is the honest outcome. Do not
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
- `volume` only -> `"Vol. 9"`. SSCL moved to continuous publication in 2020,
  so its records from then on carry `issue: null` and a whole year forms one
  group. Its 2018–2019 volumes *do* have monthly issues and group normally —
  both shapes are correct, so do not "fix" either.
- Early Access (`volume == "PP"`, `issue == 99`, or `isEarlyAccess`) is pulled
  out into a separate `early_access.json` shared across years, and rendered as
  its own page.

Early Access merges per year on write: scraping a single year must not drop
the other years' entries.

## 5. Duplicate records

A year can return the same paper twice. ISSCC 2002 returns 56 titles twice —
once under a bare `Session 0` bucket and once under the real topical session,
with *different* article numbers, and one copy missing its abstract.

`_deduplicate_papers` keeps one copy per normalised title, preferring (in
order) a real session over session 0, a present abstract, then more authors,
and renumbers what remains.

## 6. Legacy text markup

Older records carry pre-Unicode IEEE markup and undecoded HTML entities.
`textclean.py` converts both at parse time — see `01-architecture.md`.
Unknown `/spl …/` names are left untouched rather than guessed at, so an
unmapped name stays visible instead of silently becoming the wrong character.

Full abstracts from `/rest/document/<n>/abstract` carry a third kind:
JATS/MathML tags with attributes, such as `<sup xmlns:mml="…">2</sup>`,
`<inline-formula><tex-math>$N$</tex-math></inline-formula>`, `<tex>`,
`<para>`, `<xref>` and `<etal/>`. Before 2026-11-02 the cleaner knew only bare
tags. It dropped `</sup>` and left the opening tag, so 17,974 abstracts showed
raw markup. `_strip_markup` now renders them:

- formulas become their LaTeX, which MathJax draws;
- superscripts and subscripts become Unicode where it has the character, else
  `^x` / `_x`;
- references, paragraph breaks, `et al.` and links become plain text.

It also repairs the damaged form, an opening `<sup>` with no closing tag, by
taking the next token. Only listed tag names are touched, because abstracts
hold real `<` ("BER<10⁻¹²", "Ω<Re{Z}"). Checked on 2026-11-02: known-answer
cases pass, and 144,606 raw search-API texts clean exactly as before.
Stored text is re-cleaned with `tools/repair_abstract_markup.py`.

## 7. What is deliberately not inferred

Session structure is never reconstructed for years that do not expose it.
The best available heuristic (empty abstract + exactly two authors + a
topic-like title) finds 22 real CICC session breakers but also misfires on 4
genuine ISSCC papers, so it is not used. A visible topic header in the paper
list is a smaller error than a dropped paper. See
`../scratch/2026-09-20-source-audits.md`.

## 8. Known limits

- Affiliations are absent until `--enrich-affiliations` has run for that year.
- `conference_name` on a paper comes from `publicationTitle` and does not
  reliably distinguish merged VLSI tracks; the publication number does.
- Pre-2003 proceedings sometimes lack abstracts entirely; those papers are
  kept, and the gap is counted in `validation_summary.csv`.
