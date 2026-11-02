# 04 — The viewer and your marks

> **Review status:** ⏳ Unreviewed *(default; update when Yi reviews)*
>
> ✍️ Claude-authored (2026-09-20).

The generated site is plain static HTML — no build step, no server required.
Open `site/index.html` and it works from disk.

## Pages

| Page | What it does |
|---|---|
| `site/index.html` | Conference picker. |
| `site/<id>/index.html` | Year cards (**newest first**, Early Access ahead of them) + search across every paper of that source. |
| `site/<id>/year_<year>.html` | One year, grouped by session, with a filter box. |
| `site/<id>/early_access.html` | Journals only: Early Access papers, grouped by year. |
| `site/search.html` | Search across **every** source at once (see below). |
| `site/surveys/index.html` | Topic surveys: one card per survey (run date, dataset date, years, sources, counts), each linking into its report's sub-areas. Linked from `site/index.html` once a survey exists; built from `surveys/<topic>/out/` (see `surveys/README.md`). |
| `site/<id>/annotations.js` | Generated snapshot of your marks (see below). |

## Layout

The paper list is a **CSS grid, not a `<table>`**, which is what lets it
reflow. Nothing is truncated: titles, abstracts and author lists always show
in full.

| Width | Layout |
|---|---|
| ≥ 1800 px | Five columns, abstract given extra room |
| 1250–1800 px | Five columns |
| 1000–1250 px | Five columns, tighter gutters |
| 720–1000 px | Abstract drops to its own full-width line under the title |
| < 720 px | Single column; each paper becomes a labelled card |

Two independent controls, both remembered per browser:

- **Size (S/M/L)** — type size and row padding only. It never clips text.
- **Shorten abstracts** — an *opt-in* 3-line clamp for skimming long lists.
  Off by default, because the default is full visibility.

## Author affiliations

Every author name is a `<span class="author">`. When an affiliation is known
it gets a dotted underline, and hovering shows it in a tooltip (plus a native
`title` for touch and screen readers).

Affiliations do **not** come from the search API — they need one extra request
per paper against `/rest/document/<articleNumber>/authors`. Until that pass
has run for a year, names show with no underline and no tooltip, which is the
intended graceful degradation. To fill them in:

```bash
python main.py --conference jssc --enrich-affiliations --affiliation-limit 500
```

Newest years are done first, results are cached in
`cache/<id>/affiliations.json`, and re-running only fetches what is still
missing. Budget roughly **0.7–1.1 s per paper**.

## Likes, marks and notes

Each paper row carries:

- **★ like** — a toggle; liked rows get a gold edge, and both the year filter
  and the search page can show liked papers only.
- **mark** — one of `to-read`, `reading`, `read`, `important`, `reference`.
- **note** — free text, one line by default, drag to grow.

### Where they are stored

```
userdata/annotations.json        <- the single source of truth
  { "version": 1,
    "papers": {
      "<articleNumber>": { "liked": true,
                           "mark": "important",
                           "note": "compare with Lee ISSCC'24",
                           "updated": "2026-09-20T16:04:11.123Z" } } }
```

Keyed by **IEEE article number**, not by title or row position — so a mark
survives re-scrapes, renumbering and reordering. This file lives outside
`output/`; no scrape or rebuild ever writes to it. Merges are per paper, with
the newest `updated` timestamp winning, so two machines cannot clobber each
other.

### How a page reads and writes them

Reading works everywhere: the build writes `site/<id>/annotations.js`, which a
`file://` page can load (it cannot `fetch()` JSON, but it can run a script).

Writing depends on how the page was opened:

| Opened as | Writes go to | Survives across machines? |
|---|---|---|
| `http://localhost:8800` (via `serve.py`) | `userdata/annotations.json`, immediately | Yes — the sync script pushes it to iCloud |
| `file://…` (double-clicked, incl. from iCloud) | that browser's `localStorage` only | Only after you press **Export marks** |

So: **mark papers through `serve.py` on this PC** and they are saved and
synced automatically. If you mark papers on another machine straight from the
iCloud folder, press **Export marks**, drop the downloaded `annotations.json`
into the iCloud `userdata/` folder, and the next update run merges it.
**Import** does the reverse for a one-off file.

The status text beside the buttons turns amber when there are unsaved
`file://` changes.

## Global search (`site/search.html`)

One page over all ~60k papers, built by `build_global_search()` in
`html_builder.py`.

### What it loads, and when

| File | Size | Loaded |
|---|---|---|
| `search-index.js` | 18 MB | always, before the page script |
| `abstracts/<id>.js` | 24 MB total | only for the chosen sources, when a scope or the abstract column needs them |
| `affiliations/<id>.js` | 10 MB total | only for the chosen sources, when a scope, the affiliation column or the affiliation sort needs them |

All three are **JavaScript, not JSON**, and arrive through `<script src>`.
A browser refuses `fetch()`/XHR against a `file://` URL, and the viewer is
opened straight off disk — including off iCloud on another machine — so a
script tag is the only way in without running a server. Testing this with
`--allow-file-access-from-files` proves nothing: that flag turns the
restriction off.

An affiliation shard entry is `{"u": [affiliation, ...], "m": [index per
author]}` (`_affiliation_entry()`). The per-author list repeats one employer
once per co-author, so the column reads `u` while the **author tooltip**
follows `m` back to the hovered author's own entry — the same
`.author.has-affil` tooltip the year pages use. `m[i] === -1` means that
author had none.

Affiliations are wanted on every page for those tooltips, but 12 MB must not
delay the first paint, so `start()` renders from the index and only then sets
`wantAffiliations`, which brings the shards in behind the results.

**One row per paper.** The index keeps one record per article number — a net
under the Early Access handling in `docs/02-data-sources.md`, which is where
the rule itself lives. It caught 428 papers listed twice before that was
fixed at the source.

### Query syntax

| Form | Meaning |
|---|---|
| `sar adc` | all words |
| `"phase locked"` | exact phrase |
| `adc*` | starts with |
| `*sigma*` | contains |
| `sar?adc` | one character |
| `/^a \d+ bit/` | regular expression |
| `-"noise shaping"` | exclude; quotes required, so `PLL-less` and `-40` search as before |

**One typed token is one term.** `Q-enhanced` flattens to two words, but they
must stay adjacent, so it behaves exactly like `"Q-enhanced"` — unquoted,
quoted, or in the curly quotes macOS substitutes as you type (all three give 25
results). Before this, a hyphen split the term into two loose words that could
match anywhere in a title: `Q-enhanced` returned 167 results, among them a
paper matching the `Q` inside `12-DQ` and an `Enhanced` twelve words later.
`class-G` gave 1,100 against the quoted form's 48.

**A term lines up with a word edge**, start or end: `adc` finds `ADCs` and
`TIADC`, not the `adc` inside `broadcast` or `readcycle` (34 such titles). Use
`*adc*` to search inside words — that is what the wildcard is for.

A **Case sensitive** switch sits in the Show panel, off by default; it is
carried in the URL as `case=1`. With it off, both sides are lower-cased before
comparing (`adc` finds 2,695 papers); with it on they are not (`adc` finds 29,
`ADC` 2,664). The switch reaches matching and highlighting together, including
wildcards and `/regex/` written without flags of its own.

Both the query and the text are flattened to words before comparing, so
hyphens, slashes and other punctuation never decide a match:
`delta-sigma`, `delta sigma` and `delta_sigma` are one query. Highlighting
rebuilds a regexp that spans the separator (`class g` marks `Class-G`) —
matching on flattened text while highlighting raw text is what silently broke
every quoted phrase before.

### Columns

`COLUMNS` in `templates/search.html.j2` is the single source of truth: key,
label, default width in px, and whether it starts visible. Year/no., cited,
title, source and notes are on by default; abstract and affiliation are off.
**Sort → Citations** orders by IEEE Xplore citation count (index field `k`;
a paper without one sorts last). Year pages show the count under the paper
number, drawn by CSS from `data-cites` so the page's text filter does not
match it. See `05-operations.md` for refreshing the counts.

The switches live in the **Columns** menu in the toolbar, beside Sort —
not in the sidebar, which is where a reader looking at the table header does
not look.

The table fits the window. Year/no., Cited and Notes keep their pixel
width; the text columns share the rest in proportion to their set widths
(`fr`), and the table scrolls sideways inside its own box only once they
reach 60% of those widths. Fixed pixels for every column, as before
2026-10-27, overflowed at 1400 px and left an empty strip at 1920 px. A drag
first takes each column's on-screen width as its share, so the edge follows
the mouse. Dragging a header edge writes to `localStorage` under
`paperlog.search.columns`; **Reset columns** restores the defaults. The
layout is deliberately *not* in the URL — a shared link should carry the
query, not somebody else's column widths.

## Escaping

Autoescape is on for every template. This matters beyond security: EE titles
are full of `<100>` crystal orientations and `<10mV` ripple figures, which a
browser otherwise swallows as malformed tags. Two further guards:

- The embedded search payload escapes `</`, so a title cannot close the
  `<script>` block.
- Result rows set `a.href` as a property rather than building an HTML string,
  so a malformed URL cannot break out of the attribute.

## MathJax

MathJax renders `$…$` in titles and abstracts, and is told to skip
`<textarea>` so it never mangles a note you are typing.

It is **served from the site**, at `site/vendor/mathjax/tex-svg-full.js`, with
the CDN left only as a fallback if that file is missing. A CDN fails exactly
where this viewer is meant to work — off a disk, off iCloud on another
machine, behind a network that cannot reach jsdelivr — and a title then shows
its raw `${\text{dV}}_{\text{ds}}$` source. `copy_vendor_assets()` copies it
in at build time, fetching it once into `assets/` if it is not there (which is
gitignored: 2 MB of upstream Apache-2.0 bundle, not our source).

**It must be the `-full` bundle.** Plain `tex-svg.js` fetches TeX extensions
lazily, relative to its own URL, so a local copy sends the browser after
`vendor/mathjax/input/tex/extensions/boldsymbol.js` — which is not there. The
failure is not confined to that one formula: MathJax is left part-way through
the page, and every later pass dies with

```
Failed to execute 'splitText' on 'Text': The offset 123 is larger than the Text node's length.
```

so **no** title on the page renders. The misleading part is that this only
shows up with a local copy: from the CDN the extension loads and nothing goes
wrong, which is why it survived a first round of testing.

On the search page, painting and typesetting share one promise queue, so
MathJax is never walking rows that are being rebuilt under it, and its
`startup.pageReady` typesets whatever is on screen rather than sweeping the
whole document — the rows do not exist when that sweep would run.

A handful of abstracts (18 of ISSCC 2026's) carry an odd number of `$` in
IEEE's own metadata; MathJax leaves the unmatched one as a literal character.
That is upstream, not a rendering fault.
