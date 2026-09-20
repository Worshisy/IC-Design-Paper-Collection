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


---

# All nine sources audited (final)

One agent per source read every title. Everything below was re-measured before
acting, and re-verified after the fix by an offline `--reparse`.

## Corpus-wide results

| Defect | Before | After |
|---|---|---|
| Legacy `/spl …/` in titles | 8,749 (titles+abstracts) | **3** |
| Legacy `/spl …/` in abstracts | — | 91, all truncated by IEEE mid-token (unconvertible) |
| HTML entities stored encoded | 2,768 | **0** |
| Advertisement records counted as papers | 222+ | **0** |
| Journal years with out-of-order issues | many | **0** |
| Journal years with a duplicated issue label | 67 (TMTT) | **0** |
| Simple `$\Delta\Sigma$` LaTeX spans in titles | — | **0** (converted; complex spans left to MathJax) |

Final dataset: **59,463 papers**, 2,266 sessions/issues, 9 sources.

## Coverage gaps the audits exposed

| Gap | Cause | Outcome |
|---|---|---|
| TCAS-I + TCAS-II 2000–2003 empty | Renamed in 2004; pre-2004 volumes are separate publications (`81`, `82`). Querying the configured punumber returned 0 records **silently** | +1,443 papers |
| CICC 2010 absent | Indexed as "IEEE Custom Integrated Circuits Conference 2010"; the search term "CICC" never matched | recovered |
| JSSC pre-2000 | Not previously scraped | +1,260 papers (1995–1999), per-source `first_year` |
| CICC 2016 | Genuinely not in IEEE Xplore (probed four ways; 2017 control works) | documented, not fixable |
| TCAS-I 2008 Issue 12 | Absent from IEEE's own response | documented |

## Signals that turned out to matter

- **The abstract, not the title, identifies front matter.** IEEE writes fixed
  boilerplate: `"Advertisement…"`, `"Provides notice of upcoming conference
  events…"`, `"Presents a listing of the editorial board…"`. A masthead titled
  only `"IEEE JOURNAL OF SOLID-STATE CIRCUITS"` gives no title clue at all.
- **Prefix-match, never substring, for common words.** `"advertisement"`
  appearing *anywhere* in an abstract would delete real papers; an abstract
  that *begins* with it is always an advert.
- **IEEE promo records from 2023 on carry no abstract**, so the prefix rule
  cannot see them — those need an explicit title list ("TechRxiv…",
  "Introducing IEEE Collabratec", and its corrupted twin "…Collabratex").

## Deliberately left alone

- **Raw LaTeX in titles/abstracts.** MathJax renders `$…$` in the page. Only
  spans consisting purely of simple commands are converted to Unicode (better
  for search); anything with braces, sub/superscripts or unknown macros is
  left untouched, because converting it would render *worse* than MathJax.
- **Session reconstruction for CICC/RFIC/VLSI.** Measured, 4 false positives
  on real ISSCC papers. Not worth a dropped paper.
- **IEEE's own corrupt metadata**: CICC 2004 session names
  (`"Analoa technigues"`), a 2009 JSSC title in broken lowercase, `"lt;"`
  fragments from mangled `&lt;`, `"Technology Technical Sessoin"`. Silently
  "correcting" source data would be worse than showing it.
