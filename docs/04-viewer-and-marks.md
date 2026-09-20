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

## Escaping

Autoescape is on for every template. This matters beyond security: EE titles
are full of `<100>` crystal orientations and `<10mV` ripple figures, which a
browser otherwise swallows as malformed tags. Two further guards:

- The embedded search payload escapes `</`, so a title cannot close the
  `<script>` block.
- Result rows set `a.href` as a property rather than building an HTML string,
  so a malformed URL cannot break out of the attribute.

MathJax renders `$…$` in titles and abstracts, and is told to skip
`<textarea>` so it never mangles a note you are typing.
