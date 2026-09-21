from __future__ import annotations

import json
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
        for paper in session.get("papers", []):
            row = {
                "year": year_data.get("year"),
                "session_number": session_number,
                "session_code": session_code,
                "session_name": session_name,
                "paper_number": paper.get("paper_number", ""),
                "title": paper.get("title", ""),
                "abstract": paper.get("abstract", ""),
                "authors": paper.get("authors", []),
                "affiliations": paper.get("affiliations", []),
                "article_number": paper.get("article_number") or "",
                "paper_url": paper.get("paper_url") or "",
                "doi": paper.get("doi"),
                "displayed_paper_number": paper.get("displayed_paper_number"),
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
    html = template.render(conferences=conferences)
    out_path = site_root / "index.html"
    out_path.write_text(html, encoding="utf-8")
    logger.info("Wrote master index to %s", out_path)


__all__ = [
    "annotations_path",
    "write_annotations_seed",
    "build_html_for_year_range",
    "build_year_page",
    "build_index_page",
    "build_master_index",
]

