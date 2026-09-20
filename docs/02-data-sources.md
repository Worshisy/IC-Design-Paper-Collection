# 02 — Data sources

> **Review status:** ⏳ Unreviewed *(default; update when Yi reviews)*
>
> ✍️ Claude-authored (2026-09-20).

Nine sources, defined in `CONFERENCES` in `config.py` — which is the source of
truth, not this page or the README.

## The three discovery modes

How a year is turned into an IEEE publication number:

### 1. Search discovery — ISSCC, RFIC, CICC

Query the search API for the conference's term, restricted to that year and
`ContentType:Conferences`, then keep the first result whose
`publicationTitle` contains `title_contains` (lowercased, hyphens → spaces).

Costs one API call per year, and depends on IEEE's naming staying stable —
ISSCC alone has been published under at least four different title forms
(`"… Conference"`, `"… Conference Digest of Technical Papers"`,
`"… - (ISSCC) Digest of Technical Papers"`, `"… (ISSCC)"`). The substring
match is deliberately loose for that reason.

### 2. Fixed publication number — the five journals

A journal keeps one publication number forever, so the year comes from the
`ranges: ["2025_2025_Year"]` filter instead of discovery.

| Source | `fixed_punumber` |
|---|---|
| JSSC | `4` |
| SSCL | `8011414` |
| TCAS-I | `8919` |
| TCAS-II | `8920` |
| TMTT | `22` |

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
| **JSSC** | 2000– | n/a — issues | Grouped as `"Vol. 61, Issue 3"`. Has Early Access. |
| **SSCL** | 2018– | n/a — volume only | Publishes continuously: every record has `issue: null`, so groups are named `"Vol. 9"`. Has Early Access. |
| **TCAS-I** | 2000– | n/a — issues | Title has changed form several times ("Fundamental Theory and Applications" → "Regular Papers"), which is why masthead filtering is pattern-based. |
| **TCAS-II** | 2000– | n/a — issues | As above ("Analog and Digital Signal Processing" → "Express Briefs"). |
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
normal paper.

## Dataset size

Numbers below are read from each source's `validation_summary.csv` after the
full rebuild on **2026-09-20**, which is the first build with front-matter
filtering applied.

<!-- DATASET-TABLE-START -->
*(filled in by the rebuild — see the table below)*
<!-- DATASET-TABLE-END -->

Session counts are only meaningful for ISSCC (real sessions) and the journals
(one per issue). RFIC, VLSI and CICC report one `"General"` session per year,
for the reasons above.
