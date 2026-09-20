# 2026-09-20 — Per-source title audits (ISSCC, RFIC, CICC)

Three Sonnet agents read every paper title of one source each and reported
anything that was not a properly recognised paper. Every claim below was
re-measured against the data before acting on it. Findings from the remaining
six sources are appended as their audits land.

## What was acted on

| Finding | Measured | Fix |
|---|---|---|
| Pre-Unicode IEEE markup (`/spl mu/`, `/sup 2/`) | 8,749 occurrences in titles+abstracts, all 8 pre-2018 sources | `textclean.py` |
| HTML entities stored encoded | 2,768 (`&#39;` ×2168, `&#34;` ×591) | decoded at parse time |
| Front matter still counted as papers | a further 954 records | boilerplate-abstract detection + ephemera rules |
| RFIC 2004 `Session MO1A:` rows as papers | 25 rows | `ALPHA_SESSION_HEADER_RE` |
| ISSCC 2002 duplicate records | 56 titles twice, different article numbers | `_deduplicate_papers` |
| ISSCC 2025 `"2.8: Title"` prefix left in text | 14 titles | `split_number_prefix` |
| CICC 2010 missing entirely | confirmed absent | `search_terms` (see below) |

### The CICC 2010 gap

Discovery searched only for the term `"CICC"`. The 2010 proceedings are
indexed as **"IEEE Custom Integrated Circuits Conference 2010"** (publication
`5605059`), which that query never returns — so the year was never even
attempted (no `2010_errors.json` was written either). Adding
`search_terms: ["CICC", "Custom Integrated Circuits Conference"]` fixes it.

`search_terms` already existed in `ScraperConfig` and was unused — the style
review had flagged it as dead. It turned out to be exactly the right
extension point.

### CICC 2016 is genuinely not in IEEE Xplore

Probed with and without the `ContentType:Conferences` refinement, with both
the acronym and the full name, and with no year filter at all. Nothing.
A 2017 control query returns `7986634` immediately, so the method is sound.
`year_pub_overrides` was added to pin such a year if its publication number
ever turns up, without disabling discovery for the whole source the way
`year_to_pubs` does.

## What was deliberately NOT done

**Reconstructing sessions for years that have none.** CICC's audit showed
session/topic headers sitting in the paper list, identifiable by "abstract
empty + exactly two authors (the session chairs) + a topic-like title".
Measured across sources, that rule finds 22 correct CICC breakers — and
**4 false positives on real ISSCC 2002 papers**:

- *"A low-power ROM using charge recycling and charge sharing"*
- *"A CMOS differential noise-shifting colpitts VCO"*
- *"Digital logic using molecular electronics"*
- *"A smart CMOS wind sensor"*

Dropping or re-labelling a real paper is worse than leaving a topic header
visible as a paper, so the heuristic was rejected. This is the same principle
as RFIC/VLSI keeping a single "General" session: do not invent structure the
source does not expose.

The narrower signal — an abstract literally beginning *"This session
covers…"* — is real but only matches **9 records** corpus-wide, which is not
worth a special code path.

## Claims checked and found NOT to be bugs

- **"Six ISSCC years collapsed into one mega-session" is not a regression.**
  I suspected the `has_session_headers` gate added earlier that day. It is
  not: 2000/2001/2003/2006/2007/2008 have `displayed_paper_number` set on 0–3
  papers each, versus 241 of 266 in 2024. Those years expose neither session
  headers nor paper-number prefixes, so there has never been anything to infer
  from. Total ISSCC session count moved 654 → 653 across the change.
- **Mojibake**: zero U+FFFD in any source, confirming again that terminal
  garbling is a GBK console artifact.
- **CICC 2004 corrupted session names** (`"Desien for testability"`,
  `"Analoa technigues"`) are corrupt in IEEE's own metadata, not a parsing
  fault. Left alone — silently "correcting" source data would be worse.

## A false positive I introduced

While adding the ephemera rules, `^registration\b` matched the real paper
*"Registration-Free Image Alignment Processor for AR Glasses"* — `\b` matches
at the hyphen. Caught by `tools/audit_front_matter.py`, which is why the
"must NOT be filtered" cases exist. Narrowed to
`^registration\s+(desk|information|form|fees?|page|hours)`.

The unit set grew 44 → 75 cases and the sweep is now abstract-aware.
