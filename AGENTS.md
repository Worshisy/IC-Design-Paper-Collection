# AGENTS.md — IEEE paper collection

✍️ Claude-authored (2026-09-20). Restructured on 2026-11-02 to the
`/Workflow:workspace-bootstrap` layout: rules, state and one-line pitfalls only.
The old gotcha stories and the handoff log moved verbatim to
[`docs/07-history.md`](docs/07-history.md), and closed work is indexed in
[`DONE.md`](DONE.md).

## 1. What this is

A scraper and static viewer for IEEE Xplore paper metadata from 11 sources
(6 conferences, 5 journals). It produces JSON/CSV and a browsable offline
site. The code travels through GitHub and the dataset through iCloud. The
folder map is in [`README.md`](README.md#layout).

## 2. Current state

- **Python:** `D:\anaconda3\python.exe` (3.12.3) with `PYTHONIOENCODING=utf-8`.
  The `python` on PATH is 3.9 and cannot run this project.
- **Remote:** `https://github.com/Worshisy/IC-Design-Paper-Collection.git`,
  public. It holds the scraper, the viewer and the general agent docs only.
  On 2026-11-05 its history was rewritten to drop the literature-review files
  (force-push; old hashes such as `16bce73` became `98aa16b`; full backup in
  `D:\CodeProject\_backups\2026-11-05-log_paper-split\`).
- **Companion repo:** `surveys/` is the private repo
  `Worshisy/IC-Lit-Review` (topic surveys and literature reviews), nested
  here and git-ignored. Its own `AGENTS.md` holds its rules, including
  commit and push after each finished task. Reviews never go into this
  public repo. (Yi, 2026-11-05)
- **iCloud target:** `C:\Users\Yi Shen\iCloudDrive\IC_Design_Materials\Paper_Collection`.
- **Dataset:** 275 year files and 62,664 search rows including Early Access
  (`update_database.py --no-scrape`, 2026-11-10). Affiliations: 99.2% (2026-10-12). Every
  paper has an IEEE citation count (2026-10-22).
- **Abstracts:** the search API cuts them at about 400 characters. Full text
  comes from `tools/restore_abstracts.py` into `cache/<id>/abstracts_full.json`,
  and the scraper re-applies it on every write. Progress is in `ONGOING.md`.
- **Viewer:** `serve.py --host 0.0.0.0 --port 18817` runs under `pythonw` from
  the Startup shortcut "Paper viewer (LAN 18817)", so it is reachable on the
  home LAN. Marks save to `userdata/annotations.json`; highlights and
  comments on review pages (`/api/review-notes`) to `userdata/review_notes.json`.
- **IEEE pacing** (`config.py`, `utils.RateLimiter`, verified 2026-11-01):
  - a random 1-5 s gap between requests (0.45-2.25 s for author lookups), with
    a new seed every hour;
  - after a random 55-65 min of requests, a random 15-45 min rest.

  `tools/restore_abstracts.py` paces itself the same way with 1 worker. Any
  single 418/429/403/5xx, or a lost connection, slows it and pauses it; three
  in a row stop it, it tests once at 30/60/120/120 min, then exits with code 3.

## 3. Project rules (from Yi)

1. **`userdata/annotations.json` is Yi's data.** Merge per paper, newest
   `updated` wins. No scrape, rebuild or sync may overwrite it. (2026-09-20)
2. **Never commit the dataset**: `output/`, `site/`, `cache/`, `userdata/`,
   `data/session_overrides.tsv`, PDFs. This is a copyright constraint, so the
   repo holds scripts and docs only. Check `git status` before any push, and
   ask before pushing. (2026-09-20)
3. **iCloud sync runs once, as the last step**, copying changed files only;
   use `--no-sync` until then. Yi may ask for an extra sync. (2026-09-20)
   Exception: survey and review pages from the private companion repo (§2)
   go to iCloud at once; their builder copies only `site/index.html` and
   `site/surveys/`. (2026-11-03)
4. **Numbers in docs come from a run you did**, never carried forward. (2026-09-20)
5. **A `__DROP__` override is a deletion and needs Yi's word.** (2026-10-12)
6. **One sub-agent per conference year that needs special-case programme
   recovery**, rather than scripting through the years in the main session.
   Yi: *"each year you can find the material, for conf just send a sub agent
   to deal with special case, no need to have to do that with script"*.
   (2026-10-12)
7. **Slow and safe beats fast for one-off IEEE jobs.** Never two IEEE clients
   at once, and no captcha passing. Routing through another machine's IP
   (the Mac mini tunnel) only when Yi starts or approves it for that run.
   (2026-11-01)
   Route when approved (used 2026-11-10): `ssh -f -N -D 127.0.0.1:18080 yishenys-macmini`,
   then `HTTPS_PROXY=socks5h://127.0.0.1:18080` for the tool; check the exit IP
   (api.ipify.org) first, and stop the ssh process afterwards.
8. **Mark code edits `# [c]`**; Yi strips them after review.

## 4. Pitfalls (symptom → cause → fix)

Numbered as in [`docs/07-history.md`](docs/07-history.md) §1, which has the
full story of each one. Items 1-11 are the unnumbered first block there, in
order.

1. A title print dies with `UnicodeEncodeError` → the console is GBK → set `PYTHONIOENCODING=utf-8`.
2. Tags render as text, or not at all → `select_autoescape(["html"])` ignores `.html.j2` → it is `("html","xml","j2")`.
3. No affiliations in the records → the search API has none → one `/rest/document/<n>/authors` call per paper, cached.
4. Front matter passes as papers → `articleContentType` is always "Conference Paper" → detect by title and abstract boilerplate.
5. RFIC and VLSI have one "General" session → the API has no session data → recover it from the printed programme (docs/06).
6. A phantom session 122 → a performance figure read as a paper number → prefix inference needs real headers.
7. Early Access vanished → one year's scrape rewrote the shared file → it merges per year.
8. A parser change needs re-scraping → no, `main.py --conference all --reparse` from the record cache.
9. Front matter has no title clue → identify it by its abstract boilerplate.
10. `/spl mu/`, `/sup 2/` and HTML entities appear in text → `textclean.py`; unknown names are left alone.
11. A year is silently missing → the search term missed it (CICC 2010) → probe discovery before assuming IEEE lacks it.
12. `--reparse` zeroed sessions or affiliations → `reparse_year` restores the layout, drops and affiliations.
13. A re-run made a healthy year worse → the programme pass must beat the existing grouping.
14. A filter rule deletes real papers → measure it first and read the longest titles it would remove.
15. Regex escapes broke silently → bash heredocs mangle `\b` and `\\` → write scripts to a file, never a heredoc.
16. A curated list entry matched nothing → each list has an audit tool; run it after every edit.
17. A refresh flattened curated years → every year-file writer applies the whole curated layer.
18. Re-applying the layer after a scrape restored nothing → it must happen inside `scrape_year`, before the write.
19. A fix passed in isolation, then failed in sequence → test the real order of steps.
20. Journal affiliations blanked → the year file was written twice → the Early Access split happens before the single write.
21. A refresh dropped brand-new papers → `keep_articles` keeps papers unseen in the record cache.
22. An acronym misses years (A-SSCC) → probe every year; the spelled-out name finds all of them.
23. ISSCC's matcher accepted A-SSCC titles → re-read the title rules of similar sources; use `title_excludes_any`.
24. "No usable programme" after checking one or two years → run the full sweep first.
25. The programme is filed as a "Cover Page" → `_page_value` reads "c1".."c30"; read front-matter page ranges.
26. A scanned or garbled programme → render the pages to PNG and read them as images.
27. `splitlines()` cut lines at U+001C → decode the glyph shift before splitting.
28. IEEE's `startPage` can be wrong → join on title *and* page.
29. Parallel agents overwrote each other → separate scratch folders; each patch asserts its anchor once.
30. The unassigned count can rise while recovery improves → a flat year has none by construction.
31. Papers sit in the wrong session with no count showing it → join each to its printed entry (only A-SSCC is done).
32. Overrides appended papers at the end → `_print_order` places them.
33. A sub-agent's brief is too narrow → it reports instead of widening it.
34. Searches only saw the first 400 characters → the search API truncates abstracts → `tools/restore_abstracts.py`.
35. Abstracts show `<sup xmlns:mml=…>`, `<tex>`, `<inline-formula>` → the document endpoint writes JATS/MathML markup → `textclean._strip_markup`, `tools/repair_abstract_markup.py`; only listed tag names are touched, since "BER<10⁻¹²" is real text.
36. IEEE answers 418 to the whole IP for days → a run of about 46k requests at about 2/s, plus retries that hid early 418s → the pacing in §2, and stop instead of retrying.
37. Journal tutorials and reviews were missing ("…: A Tutorial", "Tutorial: …", "50 Years of …") → programme-listing title rules also matched papers → `_is_tutorial_paper` keeps records with authors and a real abstract (the prefix and "years of" forms in journals only); 34 restored on 2026-11-10.

## 5. Pointers

- Skills: `/Workflow:workspace-bootstrap` (this layout), `/Workflow:doc-style`,
  `/Workflow:codemap`, `/Paper:field-glance` and `/Paper:deep-survey` (which
  read this log).
- `surveys/README.md` (in the private companion repo, §2): topic searches and literature reviews over the log at the lowest agent-token cost; reuse it for any "find the papers that…" question.
- [`ONGOING.md`](ONGOING.md) for open threads, [`DONE.md`](DONE.md) for closed ones.
- [`docs/README.md`](docs/README.md) for the reference notes in reading order;
  [`CODEMAP.md`](CODEMAP.md) for which doc to update when a file changes.
- [`DEV_LOG.md`](DEV_LOG.md): 🟦 the earlier maintainer's log, kept as it is.
