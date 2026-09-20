from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from models import ConferenceYear, Paper, Session


logger = logging.getLogger(__name__)


# Matches session header titles returned by the IEEE Xplore API, such as:
#   "Session 1 Overview: Plenary"
#   "Session 2 Overview: Processors"
#   "ISSCC 2024 Session 3 Overview: Wearable Systems"
#   "Session 3 overview / RF: RF techniques"
#   "Session 7 overview - multimedia processing"
SESSION_HEADER_RE = re.compile(
    r"""
    (?:^.*?\s)?                 # optional prefix like "ISSCC 2024 "
    Session\s+
    (?P<number>\d+)
    \s*
    (?:Overview\s*)?
    [:\-–/]?\s*
    (?P<name>.+?)?
    \s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)

# CICC 2004-style headers put " - Session N" at the end, e.g.:
#   "Advanced MOSFET modeling - Session 2"
CICC_SESSION_TRAILER_RE = re.compile(
    r"""
    ^\s*
    (?P<name>.+?)
    \s*[-:]\s*
    Session\s+
    (?P<number>\d+)
    \s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Matches a paper number prefix at the beginning of an article title, such as:
#   "2.1 AMD Instinct MI350 Series GPUs ..."
#   "14.3 A 28nm 17.83-to-62.84TFLOPS/W Broadcast..."
PAPER_PREFIX_RE = re.compile(
    r"""^
    \s*
    (?P<num>\d+\.\d+)
    \s+
    (?P<title>.+)
    $
    """,
    re.VERBOSE,
)

# Titles to skip — structural front matter, not actual papers.
SKIP_TITLES = frozenset({
    "front cover",
    "copyright page",
    "title page",
    "table of contents",
    "awards",
    "reflections",
    "author index",
    "blank page",
    "index to authors",
    "dedication",
    "welcome!",
    "low-power analog signal processing",
    "society information",
    "the editor's corner",
    "editor's corner",
})

# Title prefixes/substrings that indicate non-paper entries.
SKIP_PREFIXES = (
    "tutorial:",
    "short course:",
    "isscc awards",
    "isscc award",
    "foreword",
    "[front",
    "[title page",
    "[copyright",
    "executive committee",
    "international technical program committee",
    "program committee",
    "time table",
    "timetable",
)

# Patterns for misc non-paper entries that appear in older years.
# IMPORTANT: must NOT match session headers like "ISSCC 2024 Session 1 Overview".
SKIP_PATTERNS = (
    re.compile(r"^isscc\s+\d{4}\s+(?!session)", re.IGNORECASE),  # "ISSCC 2011 timetable" but not session headers
    re.compile(r"^isscc\s+\d{4}$", re.IGNORECASE),                # bare "ISSCC 2024"
    re.compile(r"call for papers$", re.IGNORECASE),
    re.compile(r"^isscc glossary$", re.IGNORECASE),
    re.compile(r"^\d{4}\s+IEEE\s+International", re.IGNORECASE),
    re.compile(r"^tutorials$", re.IGNORECASE),
    re.compile(r"society information$", re.IGNORECASE),
    re.compile(r"^the editor'?s corner$", re.IGNORECASE),
    re.compile(r"^guest editorial$", re.IGNORECASE),
    re.compile(r"^editorial$", re.IGNORECASE),
)


def _normalize_whitespace(text: str) -> str:
    """Collapse internal whitespace to single spaces and strip ends."""

    return re.sub(r"\s+", " ", text).strip()


def _clean_session_name(raw_name: Optional[str]) -> str:
    """Normalise session names: remove 'Overview:' prefix."""

    if not raw_name:
        return ""
    name = raw_name.strip()
    name = re.sub(r"^Overview\s*[:\-–]\s*", "", name, flags=re.IGNORECASE)
    return name


def _is_front_matter(title: str) -> bool:
    """Check whether the title indicates structural front matter or non-paper content."""

    lower = title.lower().strip()
    if lower in SKIP_TITLES:
        return True
    if any(lower.startswith(prefix) for prefix in SKIP_PREFIXES):
        return True
    if any(pat.search(lower) for pat in SKIP_PATTERNS):
        return True
    return False


def _parse_session_header(title: str) -> Optional[Tuple[int, str]]:
    """
    Try to parse a session header from an article title.

    Returns (session_number, session_name) or None.
    """

    # Try CICC style first so that "Advanced MOSFET modeling - Session 2"
    # yields a non-empty session name.
    m2 = CICC_SESSION_TRAILER_RE.match(title)
    if m2:
        num = int(m2.group("number"))
        name = _clean_session_name(m2.group("name"))
        return num, name

    m = SESSION_HEADER_RE.match(title)
    if m:
        num = int(m.group("number"))
        name = _clean_session_name(m.group("name"))
        return num, name

    return None


def _sort_records_by_page(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Sort API records by startPage so session headers appear before their
    papers.  For some years the API returns session overview records grouped
    at the end; page-number sorting fixes the interleaving.
    """

    def _page_key(rec: Dict[str, Any]) -> int:
        try:
            return int(rec.get("startPage", 99999))
        except (ValueError, TypeError):
            return 99999

    return sorted(records, key=_page_key)


def _choose_conference_record_order(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Choose the safest order for conference parsing.

    IEEE API ordering varies by year:
    - Some years already have correct header/paper stream order (keep original).
    - Some years push many session headers to the tail (use start-page sort).
    """

    titled_records: List[Tuple[int, str]] = []
    for idx, rec in enumerate(records):
        raw_title = (rec.get("articleTitle") or "").strip()
        if not raw_title or _is_front_matter(raw_title):
            continue
        titled_records.append((idx, raw_title))

    if not titled_records:
        return records

    header_positions: List[int] = []
    header_numbers: List[int] = []
    for pos, (_, title) in enumerate(titled_records):
        header = _parse_session_header(title)
        if header is None:
            continue
        header_positions.append(pos)
        header_numbers.append(header[0])

    if not header_positions:
        return _sort_records_by_page(records)

    total = len(titled_records)
    first_header_pos = header_positions[0]
    last_header_pos = header_positions[-1]
    unique_header_count = len(set(header_numbers))
    increasing_headers = all(
        header_numbers[i] <= header_numbers[i + 1]
        for i in range(len(header_numbers) - 1)
    )

    # If headers start early and are well distributed/increasing, trust original
    # API order (better for un-prefixed papers).
    has_good_original_order = (
        unique_header_count >= 8
        and first_header_pos <= max(15, int(0.25 * total))
        and last_header_pos >= int(0.60 * total)
        and increasing_headers
    )
    if has_good_original_order:
        return records

    return _sort_records_by_page(records)


def _extract_paper(
    rec: Dict[str, Any],
    raw_title: str,
    year: int,
    session: Session,
    paper_index: int,
    conference_name: str,
    conference_dates: str,
    conference_location: str,
) -> Paper:
    """Build a Paper object from a single API record."""

    inferred_number = f"{session.session_number}.{paper_index}"

    displayed_number: Optional[str] = None
    title = raw_title
    prefix_match = PAPER_PREFIX_RE.match(raw_title)
    if prefix_match:
        displayed_number = prefix_match.group("num")
        title = prefix_match.group("title").strip()

        if displayed_number != inferred_number:
            logger.warning(
                "Paper number mismatch in session %s: displayed=%s, inferred=%s, title=%r",
                session.session_number, displayed_number, inferred_number, title,
            )

    authors: List[str] = []
    for author_obj in rec.get("authors", []):
        name = author_obj.get("preferredName") or author_obj.get("normalizedName", "")
        if name:
            authors.append(name)

    html_link = rec.get("htmlLink", "")
    paper_url: Optional[str] = None
    if html_link:
        paper_url = (
            f"https://ieeexplore.ieee.org{html_link}"
            if html_link.startswith("/") else html_link
        )

    return Paper(
        year=year,
        session_number=session.session_number,
        session_name=session.session_name,
        paper_number=inferred_number,
        inferred_paper_number=inferred_number,
        title=title,
        abstract=rec.get("abstract", "") or "",
        authors=authors,
        affiliations=[],
        author_affiliations_raw="",
        conference_name=conference_name,
        conference_dates=conference_dates,
        conference_location=conference_location,
        displayed_paper_number=displayed_number,
        paper_url=paper_url,
        doi=rec.get("doi"),
    )


def _paper_prefix_session_number(raw_title: str) -> Optional[int]:
    """Return the session number from a leading paper prefix like '12.3 ...'."""

    m = PAPER_PREFIX_RE.match(raw_title)
    if not m:
        return None
    prefix = m.group("num")
    try:
        return int(prefix.split(".", 1)[0])
    except (ValueError, IndexError):
        return None


def build_conference_year_from_api(
    records: List[Dict[str, Any]],
    year: int,
    proceedings_url: str,
    publication_number: str,
    conference_name: str = "",
    conference_dates: str = "",
    conference_location: str = "",
    group_by_issue: bool = False,
) -> ConferenceYear:
    """
    Build a ConferenceYear model from IEEE Xplore search API records.

    Handles multiple data layouts across different ISSCC years:
    - Years with session headers interspersed among papers
    - Years where session headers are grouped at the end (sorted by page)
    - Years with no session headers at all (single-session fallback)
    """

    sorted_records = _sort_records_by_page(records) if group_by_issue else _choose_conference_record_order(records)

    sessions: List[Session] = []

    # Journal mode (e.g. JSSC): group by issue / isNumber instead of sessions.
    if group_by_issue:
        issue_to_session: Dict[Tuple[Any, Any, Any], Session] = {}
        for rec in sorted_records:
            raw_title = rec.get("articleTitle", "").strip()
            if not raw_title:
                continue

            if not conference_name:
                conference_name = rec.get("publicationTitle", "")
            if not conference_dates:
                conference_dates = rec.get("publicationDate", "")

            if _is_front_matter(raw_title):
                continue

            issue_num = rec.get("issue")
            volume = rec.get("volume")
            is_number = rec.get("isNumber")

            # Early-access papers (online first) appear under a special
            # "PP/99" combination in JSSC. Group them into a dedicated
            # "Early Access" pseudo-issue instead of treating them like a
            # normal numbered issue.
            is_early = bool(rec.get("isEarlyAccess")) or str(volume).upper() == "PP" or issue_num == 99
            if is_early:
                key = ("EA", None, None)
            else:
                key = (volume, issue_num, is_number)

            if key not in issue_to_session:
                session_number = len(issue_to_session) + 1
                if is_early:
                    session_name = "Early Access"
                elif volume and issue_num:
                    session_name = f"Vol. {volume}, Issue {issue_num}"
                elif issue_num:
                    session_name = f"Issue {issue_num}"
                else:
                    session_name = "Issue"
                session = Session(
                    session_number=session_number,
                    session_code=str(session_number),
                    session_name=session_name,
                )
                issue_to_session[key] = session
                sessions.append(session)

            session = issue_to_session[key]
            idx_within_issue = len(session.papers) + 1
            paper = _extract_paper(
                rec,
                raw_title,
                year,
                session,
                idx_within_issue,
                conference_name,
                conference_dates,
                conference_location,
            )
            session.papers.append(paper)

    else:
        current_session: Optional[Session] = None
        unsorted_papers: List[Tuple[Dict[str, Any], str]] = []
        sessions_by_number: Dict[int, Session] = {}

        def _get_or_create_session(session_number: int, session_name: str = "") -> Session:
            existing = sessions_by_number.get(session_number)
            if existing is not None:
                # If we created a placeholder earlier and later discover a real name,
                # prefer the explicit header name.
                if session_name and (
                    not existing.session_name
                    or existing.session_name.lower().startswith("session ")
                ):
                    existing.session_name = session_name
                return existing

            name = session_name or f"Session {session_number}"
            created = Session(
                session_number=session_number,
                session_code=str(session_number),
                session_name=name,
            )
            sessions_by_number[session_number] = created
            sessions.append(created)
            return created

        for rec in sorted_records:
            raw_title = rec.get("articleTitle", "").strip()
            if not raw_title:
                continue

            if not conference_name:
                conference_name = rec.get("publicationTitle", "")
            if not conference_dates:
                conference_dates = rec.get("publicationDate", "")

            if _is_front_matter(raw_title):
                continue

            header = _parse_session_header(raw_title)
            if header is not None:
                session_number, session_name = header
                current_session = _get_or_create_session(session_number, session_name)
                logger.debug("Detected session header: %s (number=%s)", raw_title, session_number)
                continue

            # If a title includes an explicit paper prefix like "14.2 ...", use the
            # prefix's major number as the owning session. This guards against years
            # where API record ordering is imperfect and headers/papers are interleaved.
            prefix_session_number = _paper_prefix_session_number(raw_title)
            if prefix_session_number is not None:
                current_session = _get_or_create_session(prefix_session_number)

            if current_session is None:
                unsorted_papers.append((rec, raw_title))
                continue

            paper_index_within_session = len(current_session.papers) + 1
            paper = _extract_paper(
                rec, raw_title, year, current_session, paper_index_within_session,
                conference_name, conference_dates, conference_location,
            )
            current_session.papers.append(paper)

        # Fallback: if no session headers were found, put all papers in session 1.
        if not sessions and unsorted_papers:
            logger.info(
                "[%s] No session headers found; assigning %d papers to a single session",
                year, len(unsorted_papers),
            )
            fallback_session = Session(
                session_number=1,
                session_code="1",
                session_name="General",
            )
            sessions.append(fallback_session)
            for idx, (rec, raw_title) in enumerate(unsorted_papers, start=1):
                paper = _extract_paper(
                    rec, raw_title, year, fallback_session, idx,
                    conference_name, conference_dates, conference_location,
                )
                fallback_session.papers.append(paper)
        elif unsorted_papers:
            # Papers appeared before the first session header (rare after page sort).
            logger.warning(
                "[%s] %d papers appeared before any session header; prepending to session 1",
                year, len(unsorted_papers),
            )
            first_session = sessions[0]
            prepend: List[Paper] = []
            for idx, (rec, raw_title) in enumerate(unsorted_papers, start=1):
                paper = _extract_paper(
                    rec, raw_title, year, first_session, idx,
                    conference_name, conference_dates, conference_location,
                )
                prepend.append(paper)
            offset = len(prepend)
            for p in first_session.papers:
                new_idx = int(p.paper_number.split(".")[-1]) + offset
                p.paper_number = f"{first_session.session_number}.{new_idx}"
                p.inferred_paper_number = p.paper_number
            first_session.papers = prepend + first_session.papers

        # Keep conference sessions ordered by numeric session id.
        if sessions:
            sessions.sort(key=lambda s: s.session_number)

    conference = ConferenceYear(
        year=year,
        proceedings_url=proceedings_url,
        sessions=sessions,
        conference_name=conference_name or None,
        conference_dates=conference_dates or None,
        conference_location=conference_location or None,
    )

    _validate_conference_year(conference)
    return conference


def _validate_conference_year(conference: ConferenceYear) -> None:
    """
    Run consistency checks on a parsed ConferenceYear.

    Logs warnings for issues; does not raise so the pipeline can continue.
    """

    last_session_number = 0
    for session in conference.sessions:
        if session.session_number <= last_session_number:
            logger.warning(
                "Session numbers not strictly increasing in year %s: found %s after %s",
                conference.year,
                session.session_number,
                last_session_number,
            )
        last_session_number = session.session_number

        if not session.papers:
            logger.warning(
                "Session %s (%s) has zero papers in year %s",
                session.session_number,
                session.session_name,
                conference.year,
            )
            continue

        expected_index = 1
        for paper in session.papers:
            expected_inferred = f"{session.session_number}.{expected_index}"
            if paper.inferred_paper_number != expected_inferred:
                logger.warning(
                    "Non-contiguous numbering in year %s session %s: expected %s, found %s",
                    conference.year,
                    session.session_number,
                    expected_inferred,
                    paper.inferred_paper_number,
                )
            expected_index += 1


__all__ = [
    "SESSION_HEADER_RE",
    "PAPER_PREFIX_RE",
    "build_conference_year_from_api",
]
