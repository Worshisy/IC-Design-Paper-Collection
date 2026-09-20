# 2026-09-20 — Style/quality review of the original code

A Sonnet agent reviewed the pre-fix code (read-only) for dead code, naming,
error handling, import-time side effects, docstring accuracy, ISSCC
assumptions leaking into shared paths, and template duplication. Recorded here
so nobody re-derives it.

## Acted on

| Finding | What was done |
|---|---|
| **Autoescape never fired.** `select_autoescape(["html","xml"])` matches the *final* extension; every template ends in `.j2`. Verified: `env.autoescape("year.html.j2")` → `False`, and a `<script>` in a conference name rendered live. | Changed to `("html","xml","j2")` + `default_for_string=True`. Also fixed titles like `<100>`/`<10mV` that browsers were eating. Embedded search JSON now escapes `</`. |
| **Unescaped URL in a JS template literal** (`index.html.j2`: `` `<a href="${p.url}">` ``, with `escape()` applied to the title but not the URL). | Result rows now build the anchor as a DOM node and assign `a.href` as a property. |
| **Import-time singletons froze the ISSCC config** and created ISSCC directories for every run, whatever `--conference` said (`utils.py` `_SESSION` / `retrying_post` both call `get_config()` at import; `get_config` unconditionally `mkdir`s). | `get_config(create_dirs=False)` added and used by `utils`. `raw_html_dir` dropped from the created set (nothing writes it). |
| **Docstring contradicted code**: `build_html_for_year_range` claimed a per-conference default but hardcoded `site/isscc`. | Derives the id from the JSON path. |
| **ISSCC-only skip rules applied to every source.** | Rewritten generic — see `2026-09-20-front-matter-audit.md`. |
| **`validation.py` called `get_config()` unconditionally**, creating ISSCC dirs while validating other sources, plus a no-op `json_dir = json_dir`. | Only called when `csv_dir is None`; no-op removed. |
| Unused imports: `ensure_dir` in `scraper.py`, `Tuple` in `validation.py`. | Removed. |
| Duplicate `from validation import ...` inside the per-conference loop in `main.py`. | Hoisted to module level. |
| `return [c for c in CONFERENCES.keys()]`. | `list(CONFERENCES.keys())`. |
| **Verbatim CSS/JS duplication** between `year.html.j2` and `index.html.j2` (theme variables, MathJax config, `setupDensity`/`setupTheme` IIFEs). | Extracted into `_styles.css.j2` and `_scripts.js.j2`, included by both. |
| Per-paper INFO logging flooded the console on 13k-paper journals. | Dropped to DEBUG. |
| Bare `except Exception` swallowing the real error when loading an error report. | `except (OSError, ValueError)` with the exception in the message. |
| `import json as _json` mid-function. | Normal top-level import. |

## Found independently while fixing, not in the review

- **The retry wrappers never raised `HttpError`.** `tenacity` is configured
  with `reraise=True`, so it re-raises the *original* `requests.HTTPError`,
  never `RetryError` — which is all the `except RetryError` arms caught. Every
  `except HttpError` handler in `scraper.py` was dead, so one transient 502
  aborted a whole source. Found when IEEE started 502-ing mid-rebuild.
- **`--force-refresh` was a no-op**: stored on `Scraper`, never read, and no
  HTML cache exists for it to bypass. It now implies `--overwrite`.
- **Early Access was clobbered, not merged**, by any partial-year journal
  scrape. Reproduced live: SSCL's 2 Early Access papers went to 0 after a
  single-year re-scrape.

## Deliberately not acted on

- **`affiliations` / `author_affiliations_raw` were dead fields** (always
  `[]`/`""`, referenced by no template). The review suggested populating or
  removing them. They are now **populated** by the new affiliation pass and
  drive the hover tooltips — `affiliations` is index-aligned with `authors`.
- **`search_terms` / `title_includes_any` / `title_excludes_any` are unused**
  by every configured source, making those branches of `_is_title_match`
  unreachable. Left in place: they are the extension point for a future
  ambiguous source, and removing them would be a behaviour-neutral churn.
- `conference_name: str = "ISSCC"` defaults in `html_builder` signatures.
  Harmless (always overridden by `main.py`); changing them adds diff noise.
- `_debug_cicc_sessions.py` / `_debug_jssc_issues.py` unused `Path` imports.
  Throwaway probes; left as found.
- `SKIP_TITLES` still contains the oddly specific
  `"low-power analog signal processing"`. Origin unknown — almost certainly a
  CICC session header someone blacklisted. Kept, because removing it would
  change output for a reason nobody can currently justify.
