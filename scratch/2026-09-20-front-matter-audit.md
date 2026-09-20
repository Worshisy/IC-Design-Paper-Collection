# 2026-09-20 — Front-matter filter: what it removes, and how it was checked

## The problem

`_is_front_matter` in `parser.py` decided what counts as a paper, but its
rules named ISSCC explicitly (`^isscc\s+\d{4}`, `"isscc awards"`,
`"isscc glossary"`) while running for **every** source. RFIC, CICC and all
five journals therefore had their covers, tables of contents, author indexes,
committee lists, mastheads and advertisements counted as papers.

The API cannot help here — see `2026-09-20-api-behaviour.md` §2: every RFIC
2024 record, cover page included, reports `displayContentType: "Conference Paper"`.

## Measured effect

Sweep of all stored papers with the new rules (`tools/audit_front_matter.py`,
run 2026-09-20 against the pre-rebuild dataset):

```
  cicc       38 removed /   3490 stored  ( 1.1%)
  isscc      20 removed /   6446 stored  ( 0.3%)
  jssc      512 removed /   8820 stored  ( 5.8%)
  rfic      199 removed /   3380 stored  ( 5.9%)
  sscl       24 removed /    809 stored  ( 3.0%)
  tcas1     618 removed /   8839 stored  ( 7.0%)
  tcas2     503 removed /   9487 stored  ( 5.3%)
  tmtt      801 removed /  13354 stored  ( 6.0%)
  vlsi       92 removed /   5554 stored  ( 1.7%)
  TOTAL    2807 removed /  60179 stored  ( 4.7%)
```

Confirmed live on a re-scrape: **RFIC 2024 went from 109 "papers" to 95**,
losing exactly the cover page, two TOCs, three author/affiliation indexes,
abstract cards, abstract page, steering committee, session list, author
information page, "the end of indexes" and a plenary-speaker record.

Most frequent removals (whole corpus): `[Breaker page]` ×112,
`Information For Authors` ×86, `[Blank page]` ×73, and a long tail of
`… [advertisement]` entries.

## False positives found and fixed along the way

This is the part worth remembering — each was caught by eyeballing the
*longest* removed titles, since real paper titles are long and boilerplate is
short.

| Rule as first written | Wrongly removed | Fix |
|---|---|---|
| `^\[[^\]]+\]$` (any fully bracketed title) | `[Authors' reply to comments on "CMOS low-noise amplifier design optimization techniques"]` — a real correspondence item | Gate the bracket rule on front-matter keywords (`blank\|breaker\|front\|back\|cover\|title\|copyright\|…`) |
| bare `copyright` | *Watermarking-based copyright protection of sequential functions* | `copyright\s+(form\|page\|notice\|transfer)` |
| bare `glossary` | *A Glossary of Terms for Sigma-Delta Converters* | `glossary$` |
| `^welcome` | *Welcoming the new era of GaN power devices* | `^welcome\b` |

## A silent escaping trap, for the record

The first version of these patterns was written through a shell heredoc, and
`\\b` landed in the file as a literal **backspace character** (`\x08`). Seven
patterns were silently dead — journal mastheads sailed through — and the
regexes *looked* correct in a diff, because a terminal renders `\x08` as
nothing. It surfaced only when a masthead that obviously should have matched
did not.

Check with `repr(pattern.pattern)`, not by eye, after any scripted edit to a
regex. Better: edit regex files directly rather than through a heredoc.

## Re-running the check

```bash
D:\anaconda3\python.exe tools/audit_front_matter.py
D:\anaconda3\python.exe tools/audit_front_matter.py --show-caught 80   # more titles
```

44 unit cases, all passing as of 2026-09-20. The "must NOT be filtered" cases
encode every false positive above, so re-introducing one fails the run.
Exit code is non-zero on failure, and the sweep prints the longest removed
titles for manual inspection.

**Run it before committing any change to the skip lists.**
