from __future__ import annotations

from dataclasses import field
from typing import List, Optional

from pydantic.dataclasses import dataclass


@dataclass(slots=True)
class Paper:
    """Single ISSCC paper entry."""

    year: int
    session_number: int
    session_name: str
    paper_number: str  # canonical paper number, e.g. "2.3"
    inferred_paper_number: str  # always sequential within a session
    title: str
    abstract: str
    authors: List[str]
    # Index-aligned with `authors`: affiliations[i] belongs to authors[i].
    # Empty until the per-document authors endpoint has been fetched.
    affiliations: List[str]
    author_affiliations_raw: str
    conference_name: str
    conference_dates: str
    conference_location: str
    # Fields with defaults must come last.
    displayed_paper_number: Optional[str] = None
    paper_url: Optional[str] = None
    doi: Optional[str] = None
    article_number: Optional[str] = None
    # Printed first page; used to map papers onto the programme's sessions.
    start_page: Optional[str] = None
    # IEEE Xplore "Cited by Papers" at fetch time; tools/refresh_citations.py updates it.  # [c]
    citation_count: Optional[int] = None


@dataclass(slots=True)
class Session:
    """Session with its papers."""

    session_number: int  # numeric, e.g. 2
    session_code: str  # string form, e.g. "2"
    session_name: str
    papers: List[Paper] = field(default_factory=list)


@dataclass(slots=True)
class ConferenceYear:
    """
    Proceedings for a specific ISSCC year.

    The schema matches the user requirements and can be extended
    without breaking downstream consumers.
    """

    year: int
    proceedings_url: str
    sessions: List[Session] = field(default_factory=list)

    # Optional metadata that is convenient to hold at the year level.
    conference_name: str | None = None
    conference_dates: str | None = None
    conference_location: str | None = None

