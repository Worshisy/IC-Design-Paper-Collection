# 2026-09-20 — What the IEEE endpoints actually return

Measured against the live API on 2026-09-20. Every figure here was read from
an actual response, not estimated.

## 1. The search API omits affiliations entirely

`POST /rest/search` author objects contain only:

```json
{ "preferredName": "Yuyao Kong", "normalizedName": "Y. Kong",
  "firstName": "Yuyao", "lastName": "Kong",
  "searchablePreferredName": "Yuyao Kong", "id": 37086702111 }
```

No affiliation field, at any nesting level. The README's claim that "the
search API does not always return per-author affiliations" understated it:
it **never** does.

Affiliations come from a different endpoint:

```
GET /rest/document/<articleNumber>/authors      -> 200, ~4 KB, ~0.72 s
{ "authors": [ { "name": "Yihan Zheng",
                 "affiliation": ["School of Software, Shandong University, Jinan, China"],
                 "ringgoldId": "554964", "id": "834729062370233" } ] }
```

`GET /rest/document/<articleNumber>/metadata` returns **404** — do not use it.

Cost: one request per paper. At ~0.7 s plus a 0.4 s throttle, a full backfill
of ~57k papers is on the order of **17 hours**, which is why enrichment is a
separate, resumable, cache-backed pass rather than part of the scrape.

## 2. Content-type fields cannot identify front matter

Hoped these would classify covers/TOCs without title heuristics. They do not.

| Source | `articleContentType` | `displayContentType` |
|---|---|---|
| RFIC 2024 (109 records, incl. cover page, TOC, author index) | `Conferences` ×109 | `Conference Paper` ×109 |
| TCAS-I 2024 (first 200 records) | `Journals` ×199, `Early Access Articles` ×1 | `Journal Article` ×199, `Early Access Article` ×1 |

"RFIC 2024 Cover Page" and a real paper are both `Conference Paper`. Title
matching is the only option. Recorded so nobody retries this.

## 3. Sessions exist only for ISSCC

Checked the raw record stream per source:

- **RFIC 2024** (pub 10599936, 109 records): no `Session N` records at all.
  There is a single `"RFIC 2024 Session List"` front-matter document. Papers
  follow in page order with no grouping.
- **VLSI 2024** (pub 10631290, 249 records): no session headers. Exactly one
  title matches the paper-number prefix regex —
  `"122.7 TOPS/W Stdcell-Based DNN Accelerator Based on Transition Density"` —
  and that is a performance figure, not a paper number. It was the sole cause
  of the bogus "session 122" holding all 249 papers.
- **CICC 2024** (pub 10528947, 150 records): sessions are opened by untitled
  invited talks (e.g. `"Interferer-Tolerant RX Front-End Architectures"` at
  index 7, then its papers). Not machine-distinguishable from a paper title.
- **ISSCC**: genuine `"Session N Overview: <name>"` records. 2024 parses into
  34 named sessions.

## 4. SSCL has no issue numbers

SSCL 2026: all 68 records are `volume: "9"`, `issue: null`, one shared
`isNumber`. It publishes continuously. Grouping by `(volume, issue, isNumber)`
therefore yields a single group, previously named just `"Issue"`; now
`"Vol. 9"`.

## 5. Encoding: the terminal lies, the data is fine

Titles printed to this machine's console appear as `64��64`, `1�C1.7-GHz`,
`��-Networks`. That is **not** corrupt data — Python's stdout here defaults to
**GBK**. Checked directly:

- `U+FFFD` replacement characters in stored SSCL 2026 titles: **0 / 68**.
- Printing a title containing `U+2212` (minus sign) raises
  `UnicodeEncodeError: 'gbk' codec can't encode character '−'`.

Always `PYTHONIOENCODING=utf-8`. Never "fix" an encoding bug seen only in a
terminal.

## 6. Real markup in titles is rare; broken markup is the common case

Across all 60,193 stored papers, only **17** tag-like sequences appear in
titles or abstracts. Of those, the majority are *not* markup:

- `<100>`, `<110>` — crystal orientations
- `<10mV`, `<5dB`, `<190fs` — "less than" figures
- only 2 papers carry genuine `<italic>`/`<sub>` markup

With autoescape off, a browser ate `"A 150nA IQ, 850mA ILOAD, <10mV Ripple
Buck Converter with >90% Efficiency"` from `<10mV` onward. Turning autoescape
on fixes those titles; the cost is that the 2 genuinely-marked-up titles now
show their tags literally. Correct trade.

## 7. Throttling

Sustained scraping earns **HTTP 502 Bad Gateway** from
`https://ieeexplore.ieee.org/rest/search` — not 429. During the 2026-09-20
rebuild, every source began 502-ing after roughly 90 minutes of probing plus
scraping, and stayed down for a further extended window.

Consequences, now handled in code:

- Retry policy raised to 8 attempts with exponential backoff to 120 s.
- A year that still fails is skipped, leaving existing JSON untouched, and the
  rest of the range continues.
- For multi-track conferences, if any track fails the year is not written at
  all — half a year on disk is worse than a stale one.
