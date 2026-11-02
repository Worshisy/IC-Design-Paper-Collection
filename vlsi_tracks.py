"""
Drop VLSI Technology-track papers from the merged years.

Until 2021 the Circuits and Technology symposia were separate IEEE
publications, so config lists only the Circuits one and nothing here applies.
From 2022 they share a publication. 2025 ships a Circuits programme, which
does the filtering properly; 2022, 2023, 2024 and 2026 do not, so their two
tracks can only be told apart from the papers themselves.

The list in data/vlsi_technology_papers.txt was produced by classifying all
944 titles in those four years - circuit metrics (Gb/s, TOPS/W, SNDR, phase
noise, mm2) against process and device results (nanosheet, GAA, EUV, gate
stack, mobility, endurance). It is a fixed list of article numbers rather
than a rule, because keyword rules misclassify compute-in-memory macros and
SRAM papers, which legitimately live on both sides.

Sanity check that made the list trustworthy: the surviving Circuits counts
(117, 125, 145, 141) sit alongside VLSI 2025's 132 papers, which came from a
real programme rather than from classification.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Set, Tuple

logger = logging.getLogger(__name__)

DATA_PATH = Path(__file__).resolve().parent / "data" / "vlsi_technology_papers.txt"

_cache: Dict[int, Set[str]] | None = None


def technology_papers() -> Dict[int, Set[str]]:
    """year -> {articleNumber} for the Technology track."""

    global _cache
    if _cache is not None:
        return _cache

    mapping: Dict[int, Set[str]] = {}
    if DATA_PATH.exists():
        for line in DATA_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "|" not in line:
                continue
            year_text, article = line.split("|", 1)
            try:
                year = int(year_text)
            except ValueError:
                continue
            mapping.setdefault(year, set()).add(article.strip())
    else:
        logger.warning("VLSI track list missing: %s", DATA_PATH)

    _cache = mapping
    return mapping


def drop_technology_papers(year: int, year_data: dict) -> Tuple[int, int]:
    """
    Remove Technology papers from one VLSI year.

    Returns (sessions_removed, papers_removed). A year absent from the list -
    every pre-2022 year, plus 2025 - is left untouched.
    """

    drop = technology_papers().get(year)
    if not drop:
        return 0, 0

    kept_sessions = []
    removed_papers = removed_sessions = 0

    for session in year_data.get("sessions", []):
        kept = [
            paper for paper in session.get("papers", [])
            if str(paper.get("article_number") or "") not in drop
        ]
        removed_papers += len(session.get("papers", [])) - len(kept)
        if kept:
            session["papers"] = kept
            kept_sessions.append(session)
        else:
            removed_sessions += 1

    for position, session in enumerate(kept_sessions, start=1):
        session["session_number"] = position
        prefix = session.get("session_code") or str(position)
        for index, paper in enumerate(session["papers"], start=1):
            number = f"{prefix}.{index}"
            paper["session_number"] = position
            paper["session_name"] = session["session_name"]
            paper["paper_number"] = number
            paper["inferred_paper_number"] = number

    year_data["sessions"] = kept_sessions
    return removed_sessions, removed_papers


__all__ = ["drop_technology_papers", "technology_papers"]
