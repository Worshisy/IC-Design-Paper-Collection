from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from config import get_config
from utils import ensure_dir, load_json, save_json


logger = logging.getLogger(__name__)


def _flatten_rows_for_export(year_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Flatten a year dict into exportable tabular rows."""

    rows: List[Dict[str, Any]] = []
    year = int(year_data.get("year"))
    conference_name = year_data.get("conference_name")
    conference_dates = year_data.get("conference_dates")
    conference_location = year_data.get("conference_location")

    for session in year_data.get("sessions", []):
        session_number = session.get("session_number")
        session_name = session.get("session_name", "")
        for paper in session.get("papers", []):
            rows.append(
                {
                    "year": year,
                    "session_number": session_number,
                    "session_name": session_name,
                    "paper_number": paper.get("paper_number"),
                    "inferred_paper_number": paper.get("inferred_paper_number"),
                    "displayed_paper_number": paper.get("displayed_paper_number"),
                    "title": paper.get("title"),
                    "abstract": paper.get("abstract"),
                    "authors": "; ".join(paper.get("authors", [])),
                    "affiliations": "; ".join(paper.get("affiliations", [])),
                    "paper_url": paper.get("paper_url"),
                    "doi": paper.get("doi"),
                    "conference_name": conference_name,
                    "conference_dates": conference_dates,
                    "conference_location": conference_location,
                }
            )
    return rows


def _validate_year(
    year_data: Dict[str, Any],
    error_records: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Validate a year's data against structural and content rules.

    Returns a summary dictionary for reporting.
    """

    year = year_data.get("year")
    try:
        year_int = int(year)
    except (TypeError, ValueError):
        logger.error("Year value is not an integer: %r", year)
        year_int = -1

    if year_int < 2000:
        logger.error("Invalid year %r (must be >= 2000)", year_int)

    sessions = year_data.get("sessions", [])
    num_sessions = len(sessions)
    num_papers = 0

    missing_title_count = 0
    missing_abstract_count = 0
    missing_authors_count = 0
    numbering_mismatch_count = 0
    duplicate_paper_url_count = 0
    duplicate_paper_number_count = 0

    seen_urls: set[str] = set()
    seen_numbers: set[str] = set()

    last_session_number: Optional[int] = None

    for session in sessions:
        session_number = session.get("session_number")
        try:
            sn = int(session_number)
        except (TypeError, ValueError):
            logger.error("Non-integer session_number %r in year %s", session_number, year_int)
            numbering_mismatch_count += 1
            sn = -1

        if last_session_number is not None and sn <= last_session_number:
            logger.error(
                "Session numbers not strictly increasing in year %s: %s after %s",
                year_int,
                sn,
                last_session_number,
            )
            numbering_mismatch_count += 1
        last_session_number = sn

        papers = session.get("papers", [])
        for index, paper in enumerate(papers, start=1):
            num_papers += 1
            expected_number = f"{sn}.{index}"
            inferred = paper.get("inferred_paper_number") or ""
            canonical = paper.get("paper_number") or ""

            if inferred != expected_number or canonical != expected_number:
                logger.warning(
                    "Numbering mismatch in year %s session %s index %s: "
                    "expected=%s, inferred=%s, canonical=%s",
                    year_int,
                    sn,
                    index,
                    expected_number,
                    inferred,
                    canonical,
                )
                numbering_mismatch_count += 1

            # Duplicate paper_url within a year.
            url = paper.get("paper_url")
            if url:
                if url in seen_urls:
                    duplicate_paper_url_count += 1
                    logger.warning(
                        "Duplicate paper_url in year %s: %s", year_int, url
                    )
                else:
                    seen_urls.add(url)

            # Duplicate paper_number within a year.
            pn = canonical
            if pn:
                if pn in seen_numbers:
                    duplicate_paper_number_count += 1
                    logger.warning(
                        "Duplicate paper_number in year %s: %s", year_int, pn
                    )
                else:
                    seen_numbers.add(pn)

            # Content warnings.
            title = (paper.get("title") or "").strip()
            if not title:
                missing_title_count += 1
                logger.warning(
                    "Missing title in year %s session %s paper %s",
                    year_int,
                    sn,
                    canonical or inferred or f"index {index}",
                )

            abstract = (paper.get("abstract") or "").strip()
            if not abstract:
                missing_abstract_count += 1

            authors = paper.get("authors") or []
            if not authors:
                missing_authors_count += 1

    failed_paper_fetch_count = len(error_records or [])

    summary = {
        "year": year_int,
        "num_sessions": num_sessions,
        "num_papers": num_papers,
        "missing_title_count": missing_title_count,
        "missing_abstract_count": missing_abstract_count,
        "missing_authors_count": missing_authors_count,
        "numbering_mismatch_count": numbering_mismatch_count,
        "duplicate_paper_url_count": duplicate_paper_url_count,
        "duplicate_paper_number_count": duplicate_paper_number_count,
        "failed_paper_fetch_count": failed_paper_fetch_count,
    }
    return summary


def run_validation_and_exports(
    json_dir: Path,
    csv_dir: Optional[Path] = None,
) -> None:
    """
    Validate all per-year JSON files and export CSVs.

    Produces:
    - one CSV per year
    - combined JSON for all years
    - combined CSV for all years
    - validation summary JSON and CSV
    """

    if csv_dir is None:
        csv_dir = get_config().csv_dir

    ensure_dir(json_dir)
    ensure_dir(csv_dir)

    year_files = [
        p
        for p in json_dir.glob("*.json")
        if not p.name.endswith("_errors.json")
    ]
    if not year_files:
        logger.warning("No year JSON files found in %s", json_dir)
        return

    combined_years: List[Dict[str, Any]] = []
    combined_rows: List[Dict[str, Any]] = []
    summaries: List[Dict[str, Any]] = []

    for path in sorted(year_files):
        try:
            year = int(path.stem)
        except ValueError:
            # Skip non-year JSON.
            continue

        logger.info("Validating and exporting year %s from %s", year, path)
        year_data = load_json(path)

        # Load corresponding error report if present.
        errors_path = json_dir / f"{year}_errors.json"
        error_records: List[Dict[str, Any]] = []
        if errors_path.exists():
            try:
                loaded_errors = load_json(errors_path)
                if isinstance(loaded_errors, list):
                    error_records = loaded_errors
            except (OSError, ValueError) as exc:
                logger.warning("Failed to load error report for year %s: %s", year, exc)

        summary = _validate_year(year_data, error_records=error_records)
        summaries.append(summary)

        # Per-year CSV.
        rows = _flatten_rows_for_export(year_data)
        if rows:
            df = pd.DataFrame(rows)
            out_csv = csv_dir / f"{year}.csv"
            df.to_csv(out_csv, index=False)
            logger.info("Wrote CSV for year %s to %s", year, out_csv)
            combined_rows.extend(rows)

        combined_years.append(year_data)

    # Combined JSON of all years.
    combined_json_path = json_dir / "combined_all_years.json"
    save_json(combined_json_path, {"years": combined_years})
    logger.info("Wrote combined JSON to %s", combined_json_path)

    # Combined CSV of all years.
    if combined_rows:
        combined_df = pd.DataFrame(combined_rows)
        combined_csv_path = csv_dir / "combined_all_years.csv"
        combined_df.to_csv(combined_csv_path, index=False)
        logger.info("Wrote combined CSV to %s", combined_csv_path)

    # Validation summary report.
    summary_json_path = json_dir / "validation_summary.json"
    save_json(summary_json_path, summaries)
    logger.info("Wrote validation summary JSON to %s", summary_json_path)

    summary_csv_path = csv_dir / "validation_summary.csv"
    summary_df = pd.DataFrame(summaries)
    summary_df.to_csv(summary_csv_path, index=False)
    logger.info("Wrote validation summary CSV to %s", summary_csv_path)


__all__ = [
    "run_validation_and_exports",
]

