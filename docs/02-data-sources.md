# 02 — Data sources

> **Review status:** ⏳ Unreviewed *(default; update when Yi reviews)*
>
> ✍️ Claude-authored (2026-09-20).

Eleven sources, defined in `CONFERENCES` in `config.py` — which is the source of
truth, not this page or the README.

## The three discovery modes

How a year is turned into an IEEE publication number:

### 1. Search discovery — ISSCC, RFIC, CICC, ESSCIRC, A-SSCC

Query the search API for the conference's term, restricted to that year and
`ContentType:Conferences`, then keep the first result whose
`publicationTitle` contains `title_contains` (lowercased, hyphens → spaces).

Costs one API call per year, and depends on IEEE's naming staying stable —
ISSCC alone has been published under at least four different title forms
(`"… Conference"`, `"… Conference Digest of Technical Papers"`,
`"… - (ISSCC) Digest of Technical Papers"`, `"… (ISSCC)"`). The substring
match is deliberately loose for that reason.

### 2. Fixed publication number — the five journals

A journal normally keeps one publication number, so the year comes from the
`ranges: ["2025_2025_Year"]` filter instead of discovery.

| Source | `fixed_punumber` | Pre-2004 publication |
|---|---|---|
| JSSC | `4` | — |
| SSCL | `8011414` | — (starts 2018) |
| TCAS-I | `8919` | `81` for 2000–2003 |
| TCAS-II | `8920` | `82` for 2000–2003 |
| TMTT | `22` | — |

### A-SSCC answers to three names

The acronym alone does not find every year. `"A-SSCC"` returns nothing for
2005, 2007, 2010 or 2011; the unhyphenated `"ASSCC"` returns nothing from 2021
on. `search_terms` therefore tries both and falls back to the spelled-out
`"Asian Solid-State Circuits Conference"`, which finds all 21 years — but also
returns the Asian Control, Asian Optical Fibre and Euro-Asian Pulsed Power
conferences, so `title_contains` carries the weight of excluding them.

The title also loses its hyphens in 2012 (`"Asian Solid State Circuits
Conference"`); that costs nothing because titles are normalised with
hyphens → spaces before matching.

**ISSCC excludes it explicitly.** A-SSCC's publication title contains
"solid state circuits conference", which is exactly ISSCC's `title_contains`,
so ISSCC now carries `title_excludes_any: ["asian", "a sscc"]`. An `"ISSCC"`
query has never been observed returning an A-SSCC publication, but one record
in the wrong order would have been enough to scrape the wrong conference.

**A renamed journal is a different publication.** TCAS-I became "Regular
Papers" in 2004 and TCAS-II became "Express Briefs"; before that they were
"Fundamental Theory and Applications" (`81`) and "Analog and Digital Signal
Processing" (`82`). Querying `8919` for the year 2000 returns **zero
records** — silently, with no error — so those four years were simply absent
from the dataset until 2026-09-20. `year_pub_overrides` pins them.

When a journal year comes back empty, suspect a rename before assuming IEEE
has no data.

### 3. Hardcoded year → publications — VLSI

VLSI is not one series. Until 2021 it was **two separate proceedings each
year** (Symposium on VLSI *Circuits* and Symposium on VLSI *Technology*);
from 2022 they merged into "Symposium on VLSI Technology and Circuits".

Search discovery was abandoned here because the term "VLSI" also matches
VLSI-DAT, VLSI-TSA and VLSI-SoC — different conferences entirely. Instead
`year_to_pubs` maps each year to one or two explicit publication numbers, and
the scraper merges records from all of them.

If a year fails to fetch for a multi-track year, the year is **not written at
all** — half a year on disk is worse than a stale one.

## Per-source notes

| Source | Years | Sessions in the API? | Notes |
|---|---|---|---|
| **ISSCC** | 2000– | ✅ real `Session N Overview:` headers | The only source with true session structure. Some years return headers bunched at the end; the page-sort heuristic untangles them. |
| **RFIC** | 2000– | ❌ none | Sessions exist only in the printed programme. One `"General"` session per year is the honest result. Heavy front matter (cover, TOCs, indexes, abstract cards). |
| **CICC** | 2000– | ⚠️ implicit | Each session opens with an untitled invited talk, not machine-distinguishable from a paper. Older years used a `"<name> - Session N"` trailer, which `CICC_SESSION_TRAILER_RE` still handles. |
| **VLSI** | 2000–2025 | ❌ none | Two tracks per year until 2021, merged from 2022. See mode 3 above. |
| **ESSCIRC** | 2000-2019, 2021- | ⚠ printed programme only | **There is no 2020.** The 46th edition (Grenoble) was called off for COVID and only a virtual educational event ran, so no proceedings exist: 2019 is the 45th, 2021 the 47th, and an article search restricted to 2020 returns zero records. Merged with ESSDERC in 2024 and renamed ESSERC. |
| **A-SSCC** | 2005–2025 | ❌ none; all 21 years come back from a printed programme | Started in 2005, so `first_year` is 2005 rather than 2000. Xplore answers three different names for it (see below). 2020 is small for a reason: of the 62 papers its programme prints, **21 were published in IEEE Solid-State Circuits Letters instead of the proceedings** and are in this corpus under SSCL 2020, so the A-SSCC 2020 page shows 41 and some sessions look short (session 13 prints four papers and holds one). Xplore's 49 records for the year are complete, not a paging failure. **Its programme is published a different way almost every year** — see "Where A-SSCC's programme lives" below. No paper is unassigned. |
| **JSSC** | 2000– | n/a — issues | Grouped as `"Vol. 61, Issue 3"`. Has Early Access. |
| **SSCL** | 2018– | n/a — issues, then volume | Published discrete monthly issues in 2018–2019 (`"Vol. 1, Issue 3"`), then moved to continuous publication: from 2020 records carry `issue: null`, so a whole year is one group named `"Vol. 9"`. Both shapes are correct. Has Early Access. |
| **TCAS-I** | 2000– | n/a — issues | Renamed in 2004 ("Fundamental Theory and Applications" → "Regular Papers"), so 2000–2003 come from publication `81`. The many masthead spellings are why filtering is pattern-based. |
| **TCAS-II** | 2000– | n/a — issues | As above ("Analog and Digital Signal Processing" → "Express Briefs"), 2000–2003 from publication `82`. |
| **TMTT** | 2000– | n/a — issues | Largest source by paper count. |

`year_to_pubs` for VLSI currently stops at **2025** — 2026 must be added by
hand once IEEE publishes it, or the year will simply be absent.

## Early Access (journals)

Records with `volume == "PP"`, `issue == 99`, or `isEarlyAccess` are pulled
out of the per-year structure into a shared
`output/<id>/json/early_access.json`, and rendered as
`site/<id>/early_access.html`, listed ahead of the years on the index.

They are **merged per year** on write: scraping one year replaces only that
year's Early Access entries. (Before 2026-09-20 a single-year scrape rewrote
the whole file — reproduced live, SSCL's 2 Early Access papers went to 0.)

Early Access is transient by nature: a paper there disappears from the
collection once IEEE assigns it to a real issue, where it reappears as a
normal paper. Its article number does **not** change across that move, so a
paper present in both places is one paper, not two.

**The invariant: a year file holds issues only.** Two steps keep it true.

| Step | What it does |
|---|---|
| `_extract_early_access_from_year_data()` | Lifts any Early Access session out of the year data and merges those papers into `early_access.json`, keyed on the year being rebuilt. |
| `_prune_published_early_access()` | Drops Early Access entries that now appear in a real issue — matched on article number, DOI, or normalised title. |

The extraction runs inside `reparse_year()`, **the single place that writes a
year file**. It used to sit in `scrape_year_range()` and `reparse_all()`
instead, which left `reparse_year()` free to put the Early Access issue
straight back — and a single-year re-parse is exactly what the session work
ran, over and over. 428 papers ended up in both files (2026-09-22: JSSC 133,
TCAS-I 177, TCAS-II 53, T-MTT 66) and showed twice in the global search. Any
new path that writes a journal year file has to keep this invariant.

`_prune_published_early_access()` skips Early Access sessions when working out
what counts as published: a year file in the broken state would otherwise make
it delete the real collection instead of repairing the year.

## Dataset size

Counted from the stored year files on 2026-10-12, after A-SSCC was added.
"Sessions / issues" counts real sessions for the conferences and issues for
the journals. CICC 2016 is absent because IEEE does not index it, and ESSCIRC
2020 because that edition never took place.

<!-- DATASET-TABLE-START -->
| Source | Kind | Years | Count | Papers | Sessions / issues | No abstract | Unassigned |
|---|---|---|---|---|---|---|---|
| **ISSCC** | conference | 2000-2026 | 27 | 5,994 | 813 | 122 | 0 |
| **RFIC** | conference | 2000-2026 | 27 | 3,064 | 584 | 0 | 0 |
| **CICC** | conference | 2000-2026 | 26 | 3,587 | 609 | 2 | 3 |
| **JSSC** | journal | 1995-2026 | 32 | 9,317 | 382 | 141 | 0 |
| **SSCL** | journal | 2018-2026 | 9 | 753 | 31 | 0 | 0 |
| **TCAS-I** | journal | 2000-2026 | 27 | 9,116 | 321 | 59 | 0 |
| **TCAS-II** | journal | 2000-2026 | 27 | 9,372 | 322 | 26 | 0 |
| **TMTT** | journal | 2000-2026 | 27 | 12,606 | 321 | 65 | 0 |
| **ESSCIRC** | conference | 2000-2025 | 25 | 3,125 | 744 | 7 | 0 |
| **A-SSCC** | conference | 2005-2025 | 21 | 2,118 | 447 | 0 | 0 |
| **VLSI** | conference | 2000-2026 | 27 | 2,955 | 709 | 0 | 0 |
| **Total** | | | | **62,007** | **5,283** | 422 | **3** |
<!-- DATASET-TABLE-END -->

Unassigned papers are papers whose year has a parsed programme that does not
place them. 3 remain in the whole corpus - CICC 2018's - plus one RFIC 2006
paper left in "General"; all four are listed with their reasons in
`ONGOING.md`. A year
that is one flat group has no unassigned papers by construction, so recovering
a year can *raise* this figure before curation brings it down: A-SSCC stood at
102, rose to 143 as its last nine years were recovered, and is now 0.

### Where A-SSCC's programme lives

No two stretches of years publish it the same way. Measured 2026-10-12:

| Years | Where | How it is read |
|---|---|---|
| 2005-2006, 2008-2012, 2015-2017, 2021 | Xplore "Table of contents" | existing rules |
| 2007 | **not in Xplore**; the advance programme on the host university's site | `data/programmes.tsv` |
| 2013 | Xplore record titled "[Front matter]" (i-xl) | position matching |
| 2014 | Xplore "Table of contents", titles in a font shifted 29 codepoints | page matching |
| 2018 | Xplore "Table of Contents", **scanned, no text layer** | read as images -> overrides |
| 2019 | Xplore "Table of contents", columns extract decoupled | read as images -> overrides |
| 2020 | Xplore "Table of contents", a "Program Schedule" from p.12 | title matching |
| 2022-2023 | Xplore "Advance Program" (50-70 pages) | title matching |
| 2024 | **not in Xplore**; 29 session pages on epapers2.org | `data/programmes.tsv` |
| 2025 | Xplore record titled "A-SSCC 2025 Cover Page" (c1-c30) | title matching |

Three of these hide behind a title that says nothing - "[Front matter]",
"Cover Page", and a 25-page "Table of contents" whose programme starts on
page 12. epapers2.org hosts only 2024 and 2025; 2014-2023 return 404 there.

### A programme can be filed as a cover page

A-SSCC 2025 publishes four records titled "A-SSCC 2025 Cover Page". Three are
covers, paginated c1-c2. The fourth, article **11349376**, runs c1-c30 and is
the full programme - session names, chairs, rooms and every paper code.

Nothing in its title says so, so the only thing separating it from the three
real covers is its length, and `_page_value` could not read that length:
"c1" and "c30" are neither decimal nor roman, so the span came out 0 and the
record was never considered. It now reads cover-section pagination, which
across every cached record promotes exactly three documents - this one, a
TMTT table of contents already excluded for being over 200 pages, and a JSSC
index - and costs nothing elsewhere.
