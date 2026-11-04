from __future__ import annotations

import json
import re
import shutil
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

from config import get_config
from utils import ensure_dir, load_json


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class YearSummary:
    year: int
    total_sessions: int
    total_papers: int


def _project_root() -> Path:
    return Path(__file__).resolve().parent

def _get_templates_dir() -> Path:
    """Return the directory containing Jinja2 templates."""

    return Path(__file__).resolve().parent / "templates"


def _create_env() -> Environment:
    """Instantiate a Jinja2 environment rooted at the templates directory."""

    templates_dir = _get_templates_dir()
    loader = FileSystemLoader(str(templates_dir))
    env = Environment(
        loader=loader,
        # Templates are named "*.html.j2"; select_autoescape looks at the final
        # extension only, so "html"/"xml" alone would leave autoescape OFF and
        # interpolate API text raw. Match on the real suffix.
        autoescape=select_autoescape(
            enabled_extensions=("html", "xml", "j2"),
            default_for_string=True,
        ),
    )
    return env


def _flatten_papers(year_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Flatten sessions and papers into a list of rows for the table.

    Each row carries its own session metadata and paper fields.
    """

    rows: List[Dict[str, Any]] = []
    for session in year_data.get("sessions", []):
        session_number = session.get("session_number")
        session_name = session.get("session_name", "")
        session_code = session.get("session_code") or str(session_number)
        # Derive the displayed number here rather than trusting the stored one.
        # The header reads "Session <code>", so its papers must read
        # "<code>.1", "<code>.2" - several code paths built the stored number
        # from a positional counter instead, and the two disagreed on screen.
        for index, paper in enumerate(session.get("papers", []), start=1):
            row = {
                "year": year_data.get("year"),
                "session_number": session_number,
                "session_code": session_code,
                "session_name": session_name,
                "paper_number": f"{session_code}.{index}" if session_code else str(index),
                "title": paper.get("title", ""),
                "abstract": paper.get("abstract", ""),
                "authors": paper.get("authors", []),
                "affiliations": paper.get("affiliations", []),
                "article_number": paper.get("article_number") or "",
                "paper_url": paper.get("paper_url") or "",
                "doi": paper.get("doi"),
                "displayed_paper_number": paper.get("displayed_paper_number"),
                "citation_count": paper.get("citation_count"),  # [c]
            }
            rows.append(row)

    # Preserve original order: sessions and papers are already in-order.
    return rows


def _build_session_overview(year_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Build a simple list describing sessions for navigation."""

    overview: List[Dict[str, Any]] = []
    for session in year_data.get("sessions", []):
        papers = session.get("papers", [])
        overview.append(
            {
                "session_number": session.get("session_number"),
                "session_code": session.get("session_code") or str(session.get("session_number")),
                "session_name": session.get("session_name", ""),
                "paper_count": len(papers),
                "anchor_id": f"session-{session.get('session_number')}",
            }
        )
    return overview


def build_year_page(
    env: Environment,
    year_data: Dict[str, Any],
    output_dir: Path,
    conference_name: str = "ISSCC",
) -> YearSummary:
    """
    Render a single year's HTML table into the output directory.

    Returns a YearSummary describing the year.
    """

    ensure_dir(output_dir)

    year = int(year_data.get("year"))
    rows = _flatten_papers(year_data)
    session_overview = _build_session_overview(year_data)

    template = env.get_template("year.html.j2")
    html = template.render(
        year=year,
        conference_name=conference_name,
        total_sessions=len(session_overview),
        total_papers=len(rows),
        rows=rows,
        sessions=session_overview,
    )

    out_path = output_dir / f"year_{year}.html"
    out_path.write_text(html, encoding="utf-8")
    logger.info("Wrote year HTML for %s to %s", year, out_path)

    return YearSummary(
        year=year,
        total_sessions=len(session_overview),
        total_papers=len(rows),
    )


def build_index_page(
    env: Environment,
    summaries: Iterable[YearSummary],
    output_dir: Path,
    all_papers: Optional[List[Dict[str, Any]]] = None,
    conference_name: str = "ISSCC",
    special_entries: Optional[List[Dict[str, str]]] = None,
) -> None:
    """Render the top-level index.html listing all available years."""

    ensure_dir(output_dir)
    template = env.get_template("index.html.j2")
    # Newest year first; Early Access is prepended by the template.
    ordered = sorted(summaries, key=lambda s: s.year, reverse=True)

    # Embedded in a <script> block, so neutralise any "</script>" that could
    # appear inside a title or abstract and end the block early.
    papers_json = (
        json.dumps(all_papers or [], ensure_ascii=False, separators=(",", ":"))
        .replace("</", "<\\/")
    )

    html = template.render(
        years=ordered,
        papers_json=papers_json,
        conference_name=conference_name,
        special_entries=special_entries or [],
    )

    out_path = output_dir / "index.html"
    out_path.write_text(html, encoding="utf-8")
    logger.info("Wrote index HTML to %s", out_path)


def build_html_for_year_range(
    input_json_dir: Path,
    output_html_dir: Optional[Path] = None,
    start_year: Optional[int] = None,
    end_year: Optional[int] = None,
    conference_name: str = "ISSCC",
) -> None:
    """
    Build static HTML pages for all years in the given range.

    output_html_dir defaults to project_root/site/<conference_id> when omitted.
    """

    src_dir = input_json_dir
    if output_html_dir is None:
        # Mirror the JSON layout: output/<id>/json -> site/<id>
        conference_id = src_dir.parent.name or "isscc"
        output_html_dir = get_config(conference_id, create_dirs=False).html_dir
    ensure_dir(src_dir)
    ensure_dir(output_html_dir)

    env = _create_env()

    year_files = [
        p
        for p in src_dir.glob("*.json")
        if not p.name.endswith("_errors.json")
        and p.name != "early_access.json"
    ]
    if not year_files:
        logger.warning("No year JSON files found in %s", src_dir)
        return

    summaries: List[YearSummary] = []
    all_papers: List[Dict[str, Any]] = []

    for path in sorted(year_files, key=lambda p: p.stem):
        try:
            year = int(path.stem)
        except ValueError:
            continue

        if start_year is not None and year < start_year:
            continue
        if end_year is not None and year > end_year:
            continue

        logger.info("Rendering HTML for year %s from %s", year, path)
        year_data = load_json(path)
        summary = build_year_page(
            env=env,
            year_data=year_data,
            output_dir=output_html_dir,
            conference_name=conference_name,
        )
        summaries.append(summary)

        for session in year_data.get("sessions", []):
            for paper in session.get("papers", []):
                all_papers.append({
                    "y": year,
                    "pn": paper.get("paper_number", ""),
                    "sn": session.get("session_name", ""),
                    "t": paper.get("title", ""),
                    "ab": paper.get("abstract", ""),
                    "au": "; ".join(paper.get("authors", [])),
                    "af": paper.get("affiliations", []),
                    "id": paper.get("article_number") or "",
                    "url": paper.get("paper_url") or "",
                })

    # Optional journal-level Early Access page (parallel to years).
    special_entries: List[Dict[str, str]] = []
    early_access_path = src_dir / "early_access.json"
    if early_access_path.exists():
        early_data = load_json(early_access_path)
        papers = early_data.get("papers", [])
        if papers:
            grouped: Dict[int, List[Dict[str, Any]]] = {}
            for p in papers:
                y = int(p.get("year", 0) or 0)
                grouped.setdefault(y, []).append(p)

            ea_rows: List[Dict[str, Any]] = []
            ea_sessions: List[Dict[str, Any]] = []
            for y in sorted(grouped, reverse=True):
                papers_for_year = grouped[y]
                ea_sessions.append(
                    {
                        "session_number": y,
                        "session_name": f"Year {y}",
                        "paper_count": len(papers_for_year),
                        "anchor_id": f"session-{y}",
                    }
                )
                for idx, p in enumerate(papers_for_year, start=1):
                    ea_rows.append(
                        {
                            "year": y,
                            "session_number": y,
                            "session_name": f"Year {y}",
                            "paper_number": f"{y}.{idx}",
                            "title": p.get("title", ""),
                            "abstract": p.get("abstract", ""),
                            "authors": p.get("authors", []),
                            "affiliations": p.get("affiliations", []),
                            "article_number": p.get("article_number") or "",
                            "paper_url": p.get("paper_url") or "",
                        }
                    )
                    all_papers.append(
                        {
                            "y": y,
                            "pn": f"{y}.{idx}",
                            "sn": "Early Access",
                            "t": p.get("title", ""),
                            "ab": p.get("abstract", ""),
                            "au": "; ".join(p.get("authors", [])),
                            "af": p.get("affiliations", []),
                            "id": p.get("article_number") or "",
                            "url": p.get("paper_url") or "",
                        }
                    )

            template = env.get_template("year.html.j2")
            html = template.render(
                year="Early Access",
                conference_name=conference_name,
                total_sessions=len(ea_sessions),
                total_papers=len(ea_rows),
                rows=ea_rows,
                sessions=ea_sessions,
            )
            out_path = output_html_dir / "early_access.html"
            out_path.write_text(html, encoding="utf-8")
            logger.info("Wrote Early Access HTML to %s", out_path)
            special_entries.append(
                {"label": "Early Access", "href": "early_access.html", "meta": f"{len(ea_rows)} papers"}
            )

    write_annotations_seed(output_html_dir)

    if summaries:
        build_index_page(
            env=env,
            summaries=summaries,
            output_dir=output_html_dir,
            all_papers=all_papers,
            conference_name=conference_name,
            special_entries=special_entries,
        )
    else:
        logger.warning("No summaries generated; index.html will not be created.")


def annotations_path() -> Path:
    """Single source of truth for user marks, kept out of the scraped data."""

    return get_config(create_dirs=False).project_root / "userdata" / "annotations.json"


def write_annotations_seed(output_dir: Path) -> None:
    """
    Write annotations.js next to the pages.

    Pages opened with file:// cannot fetch JSON, so the marks ship as a plain
    script that assigns a global. Always written (empty when there are no
    marks) so the <script src> never 404s.
    """

    payload: Dict[str, Any] = {"version": 1, "papers": {}}
    src = annotations_path()
    if src.exists():
        try:
            loaded = load_json(src)
            if isinstance(loaded, dict) and isinstance(loaded.get("papers"), dict):
                payload = loaded
        except (OSError, ValueError) as exc:
            logger.warning("Could not read %s: %s", src, exc)

    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    (output_dir / "annotations.js").write_text(
        "window.ANNOTATIONS_SEED = " + body + ";\n", encoding="utf-8"
    )


def build_master_index(site_root: Path, conference_ids: List[str]) -> None:
    """Write site_root/index.html linking to each conference's index (e.g. isscc/index.html)."""

    from config import CONFERENCES

    ensure_dir(site_root)
    template = _create_env().get_template("master_index.html.j2")
    conferences = [
        {"id": cid, "name": CONFERENCES[cid]["name"]}
        for cid in conference_ids
        if cid in CONFERENCES
    ]
    n_surveys = build_surveys_index(site_root)  # [c]
    html = template.render(conferences=conferences, n_surveys=n_surveys)
    out_path = site_root / "index.html"
    out_path.write_text(html, encoding="utf-8")
    logger.info("Wrote master index to %s", out_path)


def build_surveys_index(site_root: Path) -> int:  # [c]
    """Copy each finished topic survey (surveys/<topic>/out/) into site/surveys/ and write its index."""

    import json
    import shutil

    metas = []
    for meta_path in sorted((_project_root() / "surveys").glob("*/out/meta.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        report = meta_path.parent / meta["report"]
        if not report.exists():
            continue
        ensure_dir(site_root / "surveys")
        shutil.copy2(report, site_root / "surveys" / report.name)
        for page in (meta.get("reviews") or {}).values():   # literature reviews built on the survey  [c]
            if (meta_path.parent / page).exists():
                shutil.copy2(meta_path.parent / page, site_root / "surveys" / page)
        if (meta_path.parent / "fig").is_dir():             # paper figures embedded in Mid+ reviews  [c]
            shutil.copytree(meta_path.parent / "fig", site_root / "surveys" / "fig" / meta_path.parent.parent.name,
                            dirs_exist_ok=True)                 # one folder per topic: W ids repeat across topics  [c]
        metas.append(meta)
    if not metas:
        return 0
    metas.sort(key=lambda m: m.get("candidates_run", ""), reverse=True)
    html = _create_env().get_template("surveys_index.html.j2").render(surveys=metas)
    (site_root / "surveys" / "index.html").write_text(html, encoding="utf-8")
    logger.info("Wrote %d topic survey(s) to %s", len(metas), site_root / "surveys")
    return len(metas)




def _affiliation_entry(paper: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Distinct affiliations plus one index per author.

    ``{"u": [affiliation, ...], "m": [index per author]}``. The per-author list
    repeats the same employer once per co-author, so the column reads the
    unique list while the author tooltip follows ``m`` back to each author's
    own entry. An index of -1 means that author had no affiliation.
    """
    unique: List[str] = []
    per_author: List[int] = []
    for name in paper.get("affiliations") or []:
        name = (name or "").strip()
        if not name:
            per_author.append(-1)
            continue
        if name not in unique:
            unique.append(name)
        per_author.append(unique.index(name))
    if unique:
        return {"u": unique, "m": per_author}

    # Papers scraped before per-author parsing existed keep only the raw
    # string: good enough for the column, but there is nothing to hover.
    raw = (paper.get("author_affiliations_raw") or "").strip()
    return {"u": [raw], "m": []} if raw else None



MATHJAX_CDN = "https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-svg-full.js"


def copy_vendor_assets(site_root: Path) -> None:
    """Put MathJax inside the site.

    Every page used to pull it from a CDN, which fails exactly where this
    viewer is meant to work: off a disk, off iCloud on another machine, on a
    network that cannot reach jsdelivr. A title then shows its raw
    ``${\\text{dV}}_{\\text{ds}}$`` source. The copy under ``assets/`` is
    fetched once, and the CDN stays as the fallback in the page itself.

    It must be the ``-full`` bundle. The plain ``tex-svg.js`` fetches TeX
    extensions lazily, relative to its own URL, so a local copy sends the
    browser after ``vendor/mathjax/input/tex/extensions/boldsymbol.js`` -
    which is not there. That failure leaves MathJax half-way through the page
    and every later pass dies on an offset into a text node it has already
    rewritten, so no title on the page renders at all.
    """

    source = _project_root() / "assets" / "mathjax" / "tex-svg-full.js"
    if not source.exists():
        ensure_dir(source.parent)
        try:
            import urllib.request

            logger.info("Fetching MathJax once into %s", source)
            with urllib.request.urlopen(MATHJAX_CDN, timeout=60) as response:
                source.write_bytes(response.read())
        except Exception as exc:  # offline: the page falls back to the CDN
            logger.warning("Could not fetch MathJax (%s); pages will use the CDN.", exc)
            return

    target = site_root / "vendor" / "mathjax" / "tex-svg-full.js"
    ensure_dir(target.parent)
    if not target.exists() or target.stat().st_size != source.stat().st_size:
        shutil.copyfile(source, target)
        logger.info("Copied MathJax into %s", target)


def _citation_dates() -> Dict[str, Dict[str, str]]:  # [c]
    path = Path(__file__).resolve().parent / "output" / "citations_updated.json"
    try:
        data = load_json(path) if path.exists() else {}
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def build_global_search(site_root: Path, conference_ids: List[str]) -> None:
    """
    Write a search page covering every source, plus the index it reads.

    The index carries titles, authors and metadata only - about 12 MB across
    60k papers, which a browser loads without complaint. Abstracts are another
    24 MB, so they ship as one file per source and are fetched only if the
    reader switches abstract searching on.
    """

    from config import CONFERENCES, get_config

    ensure_dir(site_root)
    records: List[Dict[str, Any]] = []
    abstracts: Dict[str, Dict[str, str]] = {}
    affiliations: Dict[str, Dict[str, Any]] = {}

    for conference_id in conference_ids:
        if conference_id not in CONFERENCES:
            continue
        config = get_config(conference_id, create_dirs=False)
        if not config.json_dir.exists():
            continue
        per_source: Dict[str, str] = {}
        # A journal's early-access file repeats papers that the year file
        # already carries in its "Early Access" session, so the index would
        # list them twice. The year record wins: it is what the year page,
        # which the row links to, actually shows.
        seen_articles: set = set()
        per_affil: Dict[str, Any] = {}

        for path in sorted(config.json_dir.glob("*.json")):
            if not re.fullmatch(r"\d{4}", path.stem):
                continue
            try:
                data = load_json(path)
            except (OSError, ValueError):
                continue
            if not isinstance(data, dict):
                continue
            year = data.get("year") or int(path.stem)
            for session in data.get("sessions", []):
                for paper in session.get("papers", []):
                    article = str(paper.get("article_number") or "")
                    if article:
                        if article in seen_articles:
                            continue
                        seen_articles.add(article)
                    records.append({
                        "i": article,
                        "s": conference_id,
                        "y": year,
                        "t": paper.get("title", ""),
                        "a": "; ".join(paper.get("authors", [])),
                        "n": session.get("session_name", ""),
                        "c": session.get("session_code", ""),
                        "p": paper.get("paper_number", ""),
                        "u": paper.get("paper_url") or "",
                        "k": paper.get("citation_count"),  # [c]
                    })
                    abstract = (paper.get("abstract") or "").strip()
                    if abstract and article:
                        per_source[article] = abstract
                    affil = _affiliation_entry(paper)
                    if affil and article:
                        per_affil[article] = affil

        early = config.json_dir / "early_access.json"
        if early.exists():
            try:
                early_data = load_json(early)
            except (OSError, ValueError):
                early_data = {}
            for paper in early_data.get("papers", []):
                article = str(paper.get("article_number") or "")
                if article:
                    if article in seen_articles:
                        continue
                    seen_articles.add(article)
                records.append({
                    "i": article,
                    "s": conference_id,
                    "y": paper.get("year") or 0,
                    "t": paper.get("title", ""),
                    "a": "; ".join(paper.get("authors", [])),
                    "n": "Early Access",
                    "c": "",
                    "p": "",
                    "u": paper.get("paper_url") or "",
                    "k": paper.get("citation_count"),  # [c]
                })
                abstract = (paper.get("abstract") or "").strip()
                if abstract and article:
                    per_source[article] = abstract
                affil = _affiliation_entry(paper)
                if affil and article:
                    per_affil[article] = affil

        if per_source:
            abstracts[conference_id] = per_source
        if per_affil:
            affiliations[conference_id] = per_affil

    # Written as JavaScript, not JSON, and loaded with a <script> tag. The
    # viewer is opened straight off disk (and off iCloud on another machine),
    # and browsers refuse fetch()/XHR against file:// URLs - a script tag is
    # the only way to bring data in without running a server.
    payload = json.dumps(records, ensure_ascii=False, separators=(",", ":"))
    (site_root / "search-index.js").write_text(
        "window.SEARCH_INDEX=" + payload + ";", encoding="utf-8"
    )

    abstract_dir = site_root / "abstracts"
    ensure_dir(abstract_dir)
    for conference_id, mapping in abstracts.items():
        body = json.dumps(mapping, ensure_ascii=False, separators=(",", ":"))
        (abstract_dir / f"{conference_id}.js").write_text(
            "window.SEARCH_ABSTRACTS=window.SEARCH_ABSTRACTS||{};"
            f'window.SEARCH_ABSTRACTS["{conference_id}"]=' + body + ";",
            encoding="utf-8",
        )
        # Remove the JSON left by earlier builds so the two cannot diverge.
        stale = abstract_dir / f"{conference_id}.json"
        if stale.exists():
            stale.unlink()
    # Affiliations are another 10 MB, so they follow the abstracts' pattern:
    # one file per source, loaded only when a column or a scope asks for them.
    affil_dir = site_root / "affiliations"
    ensure_dir(affil_dir)
    for conference_id, mapping in affiliations.items():
        body = json.dumps(mapping, ensure_ascii=False, separators=(",", ":"))
        (affil_dir / f"{conference_id}.js").write_text(
            "window.SEARCH_AFFILS=window.SEARCH_AFFILS||{};"
            f'window.SEARCH_AFFILS["{conference_id}"]=' + body + ";",
            encoding="utf-8",
        )

    stale_index = site_root / "search-index.json"
    if stale_index.exists():
        stale_index.unlink()

    sources = [
        {"id": cid, "name": CONFERENCES[cid]["name"]}
        for cid in conference_ids
        if cid in CONFERENCES
    ]
    years = sorted({r["y"] for r in records if r["y"]})
    # Fetch dates written by tools/refresh_citations.py.  # [c]
    fetched = sorted({
        date for per_year in (_citation_dates().values()) for date in per_year.values()
    })
    html = _create_env().get_template("search.html.j2").render(
        sources=sources,
        min_year=years[0] if years else 0,
        max_year=years[-1] if years else 0,
        total_papers=len(records),
        citations_asof=(fetched[0] if len(set(fetched)) == 1 else
                        f"{fetched[0]} to {fetched[-1]}") if fetched else "",  # [c]
    )
    (site_root / "search.html").write_text(html, encoding="utf-8")
    logger.info(
        "Wrote global search over %d papers (%d abstract, %d affiliation shards)",
        len(records), len(abstracts), len(affiliations),
    )

__all__ = [
    "annotations_path",
    "write_annotations_seed",
    "build_html_for_year_range",
    "build_year_page",
    "build_index_page",
    "build_master_index",
    "build_global_search",
    "copy_vendor_assets",
]

