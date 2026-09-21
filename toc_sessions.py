"""
Recover conference session structure from the proceedings Table of Contents.

The IEEE search API exposes session headers only for ISSCC. RFIC, CICC and
VLSI look session-less through that API - but they are not. Each proceedings
ships a programme document ("Table of Contents", "Program File", "Session
List") as an ordinary front-matter record, and the sessions are printed in it.

That PDF is fetchable without a subscription, and its URL is constructible
from fields already in the cached records:

    /ielx8/<publicationNumber>/<isNumber>/<articleNumber>.pdf

Two layouts are handled, because the conferences do not agree:

* **CODE** (CICC): papers are numbered "5-1:", "5-2:" inside the text, so the
  session number is in the code itself, and "Session 5: Frequency Reference"
  gives the name. Papers are matched to records by title.
* **PAGE** (RFIC): a session header block is followed by "Page 7", "Page 11"
  markers, one per paper. Those line up with each record's `startPage`, so
  papers are matched by page - which is exact.

Whichever strategy maps more papers wins; if neither maps a reasonable share,
the year keeps its single "General" session rather than being given invented
structure.
"""

from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from utils import HttpError, get_session, load_json, save_json

logger = logging.getLogger(__name__)

# Front-matter titles that hold the programme, best candidate first.
# Front matter that is long but is NOT a programme - never pick these.
NON_PROGRAMME_RE = re.compile(
    r"(author|affiliation|subject|keyword)\s+index|^index|abstract\s+cards?",
    re.IGNORECASE,
)

TOC_TITLES = (
    "session list",
    "program file",
    "table of contents",
    "program",
    "advance program",
    "technical program",
)

# "Session 12: High-speed Wireline"
NUMBERED_SESSION_RE = re.compile(
    r"^\s*(?:\d{1,2}:\d{2}\s*[ap]m\s+)?Session\s+(\d{1,3})\s*[:.\-]\s*(?P<name>.+?)\s*$",
    re.IGNORECASE,
)
# "5-1:" or "ES3-1:" - the session number lives in the paper's own code.
PAPER_CODE_RE = re.compile(r"\b(?:ES)?(\d{1,2})-(\d{1,3}):\s*(?P<title>.*)$")
# RFIC: "Mo1B : Advanced LC-VCO Topologies"
LETTER_SESSION_RE = re.compile(
    r"^\s*(?P<code>[A-Z][A-Za-z]{0,3}\d{1,2}[A-Z]?)\s*:\s*(?P<name>.+?)\s*$"
)
# "SESSION 1" alone on a line, with the name a line or two below (VLSI, older years).
BARE_SESSION_RE = re.compile(r"^\s*SESSION\s+(\d{1,3})\s*$", re.IGNORECASE)
# "1.1 - 8:35 a.m." - dotted code, en-dash separator (VLSI, older years).
DOTTED_CODE_RE = re.compile(r"^\s*(\d{1,2})\.(\d{1,3})\s*[\u2013\u2014-]")
PAGE_MARKER_RE = re.compile(r"^\s*Page\s+(\d{1,5})\s*$", re.IGNORECASE)
CHAIR_RE = re.compile(r"^\s*(?:Chair|Chaired by|Co-Chair)", re.IGNORECASE)
# The metadata block that follows a session heading in ESSCIRC/ESSERC.
SESSION_BLOCK_RE = re.compile(r"^\s*(?:Date|Room|Time)\s*:", re.IGNORECASE)

# Noise that appears in front of a real title.
TITLE_NOISE_RE = re.compile(
    r"^\s*(?:\(\s*BEST[^)]*\)|\(\s*INVITED[^)]*\)|C\s+|»\s*)\s*", re.IGNORECASE
)


@dataclass(slots=True)
class TocPaper:
    title: str
    session_number: Optional[int] = None
    page: Optional[int] = None


@dataclass(slots=True)
class TocProgramme:
    session_names: Dict[int, str] = field(default_factory=dict)
    papers: List[TocPaper] = field(default_factory=list)
    page_sessions: List[Tuple[int, int]] = field(default_factory=list)  # (page, session)
    header_offsets: List[Tuple[int, int, str]] = field(default_factory=list)  # (line, number, name)


# ----------------------------------------------------------------------
# Fetching
# ----------------------------------------------------------------------

def find_toc_records(records: List[Dict[str, Any]], limit: int = 3) -> List[Dict[str, Any]]:
    """
    Rank the records that might be the printed programme, best first.

    Returns a LIST rather than one pick, because the obvious title is not
    always the useful document: RFIC ships both a 2-page "Session List" (which
    carries no parseable structure) and a 32-page "Table of Contents" (which
    carries all of it). The caller tries each until one yields sessions.

    Ranking is by size among plausible candidates - a programme is long, an
    index is longer still but is excluded by name, and a cover is short.
    """

    def span_of(record: Dict[str, Any]) -> int:
        try:
            return int(record.get("endPage", 0)) - int(record.get("startPage", 0))
        except (TypeError, ValueError):
            return 0

    candidates: List[Tuple[int, Dict[str, Any]]] = []
    for record in records:
        title = (record.get("articleTitle") or "").strip().lower()
        span = span_of(record)
        if NON_PROGRAMME_RE.search(title) or span > 200:
            continue
        named = title in TOC_TITLES
        if not named and (span < 8 or record.get("authors")):
            continue
        candidates.append((-span, record))

    candidates.sort(key=lambda item: item[0])
    return [record for _, record in candidates[:limit]]


def find_toc_record(records: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Best single programme candidate (kept for callers that want just one)."""

    found = find_toc_records(records, limit=1)
    return found[0] if found else None


# The viewer page embeds the real PDF path, whose /ielxN/ generation varies by
# era - ielx8 only covers recent years, which is why hardcoding it 404s on
# anything older.
PDF_HREF_RE = re.compile(r"""(https?://[^"']*?/iel[a-z]*\d*/[^"']+?\.pdf[^"']*)""")


def toc_pdf_url(record: Dict[str, Any], rate_limit: float = 1.5) -> Optional[str]:
    """
    Resolve the real PDF URL for a record via its viewer page.

    Building "/ielx8/<pub>/<issue>/<article>.pdf" by hand works for recent
    proceedings and 404s for older ones, because IEEE files them under
    different ielx generations. The stamp.jsp wrapper names the correct path,
    so ask it rather than guess.
    """

    from utils import RATE_LIMITER

    article = record.get("articleNumber")
    if not article:
        return None

    RATE_LIMITER.wait(rate_limit)
    try:
        response = get_session().get(
            f"https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber={article}",
            timeout=30,
        )
    except Exception:
        return None
    if response.status_code != 200:
        return None

    match = PDF_HREF_RE.search(response.text)
    return match.group(1) if match else None


def download_toc(record: Dict[str, Any], cache_path: Path, rate_limit: float = 1.5) -> Optional[bytes]:
    """Fetch the programme PDF, caching it so a re-parse needs no network."""

    if cache_path.exists():
        data = cache_path.read_bytes()
        if data[:5] == b"%PDF-":
            return data

    url = toc_pdf_url(record, rate_limit)
    if not url:
        return None

    from utils import RATE_LIMITER

    RATE_LIMITER.wait(rate_limit)
    try:
        response = get_session().get(
            url,
            timeout=90,
            headers={"Referer": f"https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber={record.get('articleNumber')}"},
        )
    except Exception as exc:
        raise HttpError(f"Failed to fetch TOC {url!r}: {exc}") from exc

    if response.status_code != 200 or response.content[:5] != b"%PDF-":
        logger.warning(
            "Programme download for article %s returned %s (%s bytes)",
            record.get("articleNumber"), response.status_code, len(response.content),
        )
        return None

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(response.content)
    return response.content


def fetch_major_topics(publication: str, issue: str, rate_limit: float = 1.5) -> Dict[str, str]:
    """
    Session per article from the proceedings TOC endpoint.

    POST /rest/search/pub/<pub>/issue/<isnumber>/toc returns a `majorTopic`
    field the ordinary search API omits, holding the full session heading
    ("Session 31: Noise-Shaping ADCs"). This is how IEEE Xplore renders the
    session bars on its own proceedings page, so it is authoritative where it
    exists. Returns {articleNumber: heading}; empty when the conference does
    not populate it (RFIC and VLSI do not).
    """

    from utils import RATE_LIMITER

    url = f"https://ieeexplore.ieee.org/rest/search/pub/{publication}/issue/{issue}/toc"
    session = get_session()
    topics: Dict[str, str] = {}
    page, total = 1, 1
    while page <= total and page <= 20:
        RATE_LIMITER.wait(rate_limit)
        try:
            response = session.post(
                url,
                json={
                    "isnumber": str(issue),
                    "punumber": str(publication),
                    "sortType": "sequence-asc",
                    "rowsPerPage": "100",
                    "pageNumber": str(page),
                },
                headers={
                    "Referer": f"https://ieeexplore.ieee.org/xpl/conhome/{publication}/proceeding"
                },
                timeout=40,
            )
        except Exception as exc:
            raise HttpError(f"TOC endpoint failed: {exc}") from exc
        if response.status_code != 200:
            return {}
        try:
            payload = response.json()
        except ValueError:
            return {}
        total = payload.get("totalPages", 1)
        for record in payload.get("records", []):
            heading = (record.get("majorTopic") or "").strip()
            article = str(record.get("articleNumber") or "")
            if heading and article:
                topics[article] = heading
        page += 1
    return topics


def sessions_from_major_topics(
    year_data: Dict[str, Any],
    topics: Dict[str, str],
    min_coverage: float = 0.5,
) -> Tuple[bool, str]:
    """Re-group a year using IEEE's own per-article session headings."""

    papers = [p for s in year_data.get("sessions", []) for p in s.get("papers", [])]
    if not papers or not topics:
        return False, "no headings"

    matched = [p for p in papers if topics.get(str(p.get("article_number") or ""))]
    coverage = len(matched) / len(papers)
    if coverage < min_coverage:
        return False, f"headings cover only {coverage:.0%} of papers"

    def sort_key(heading: str) -> Tuple[int, str]:
        found = re.match(r"\s*Session\s+(\d+)", heading, re.IGNORECASE)
        return (int(found.group(1)) if found else 10_000, heading)

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for paper in papers:
        heading = topics.get(str(paper.get("article_number") or "")) or "Unassigned"
        grouped.setdefault(heading, []).append(paper)

    ordered: List[Dict[str, Any]] = []
    for position, heading in enumerate(sorted(grouped, key=sort_key), start=1):
        # "Session 31: Noise-Shaping ADCs" -> keep the descriptive half.
        name = re.sub(r"^\s*Session\s+\d+\s*[:.\-]\s*", "", heading).strip() or heading
        session = {
            "session_number": position,
            "session_code": str(position),
            "session_name": name,
            "papers": grouped[heading],
        }
        for index, paper in enumerate(session["papers"], start=1):
            paper["session_number"] = position
            paper["session_name"] = name
            paper["paper_number"] = f"{position}.{index}"
            paper["inferred_paper_number"] = f"{position}.{index}"
        ordered.append(session)

    year_data["sessions"] = ordered
    return True, f"TOC headings, {coverage:.0%} of papers, {len(ordered)} sessions"


def extract_text(pdf_bytes: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        logger.warning("pypdf is not installed; cannot read the programme PDF.")
        return ""
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception as exc:
        logger.warning("Could not read the programme PDF: %s", exc)
        return ""


# ----------------------------------------------------------------------
# Parsing
# ----------------------------------------------------------------------

def _clean_title(text: str) -> str:
    return TITLE_NOISE_RE.sub("", text or "").strip()


def normalise(title: str) -> str:
    """Comparison key: lowercase alphanumerics only."""

    return re.sub(r"[^a-z0-9]+", "", (title or "").lower())


def _normalised_with_map(text: str) -> Tuple[str, List[int]]:
    """Lowercase alphanumeric text plus a map back to original offsets."""

    chars: List[str] = []
    offsets: List[int] = []
    for index, char in enumerate(text):
        if char.isalnum():
            chars.append(char.lower())
            offsets.append(index)
    return "".join(chars), offsets


def match_by_position(
    papers: List[Dict[str, Any]],
    text: str,
    extra_headers: Optional[List[Tuple[int, int, str]]] = None,
) -> Tuple[Dict[int, int], Dict[int, str]]:
    """
    Assign papers to sessions by where their titles sit in the programme.

    Some programmes (VLSI) are navigation documents: they name every session
    and print every title, but carry no page markers and no paper codes, so
    neither of the other strategies can see them. Reading position works
    instead - a paper belongs to the last session heading printed above it.

    Matching is done against the titles we already hold, rather than trying to
    guess which lines of the PDF are titles, which is what makes it reliable.
    """

    flat, offsets = _normalised_with_map(text)
    if not flat:
        return {}, {}

    # Session headings and where they start, in reading order.
    headings: List[Tuple[int, int, str]] = []   # (flat offset, number, name)
    pattern = (r"Session\s+(\d{1,3})\s*[-:.]\s*([^\n]{3,90})"
               r"|SESSION\s+(\d{1,3})\s*\n\s*\n?\s*([^\n]{3,90})")
    for match in re.finditer(pattern, text, re.IGNORECASE):
        number = match.group(1) or match.group(3)
        name = (match.group(2) or match.group(4) or "").strip()
        if not number or not name or name.lower().startswith("list"):
            continue
        flat_at = _flat_offset(offsets, match.start())
        headings.append((flat_at, int(number), name))
    # Headers found line-wise by parse_programme (ESSCIRC/ESSERC style).
    if extra_headers:
        line_starts: List[int] = []
        running = 0
        for line in text.splitlines():
            line_starts.append(running)
            running += len(line) + 1
        for line_index, number, name in extra_headers:
            if 0 <= line_index < len(line_starts):
                headings.append(
                    (_flat_offset(offsets, line_starts[line_index]), number, name)
                )

    headings.sort()
    if not headings:
        return {}, {}

    names = {number: name for _, number, name in headings}
    mapping: Dict[int, int] = {}
    for paper in papers:
        key = normalise(paper.get("title", ""))[:40]
        if len(key) < 25:
            continue
        at = flat.find(key)
        if at < 0:
            continue
        owner = None
        for flat_at, number, _ in headings:
            if flat_at <= at:
                owner = number
            else:
                break
        if owner is not None:
            mapping[id(paper)] = owner
    return mapping, names


def _flat_offset(offsets: List[int], raw_index: int) -> int:
    import bisect
    return bisect.bisect_left(offsets, raw_index)


def _next_nonempty(lines: List[str], index: int) -> str:
    for line in lines[index + 1: index + 4]:
        if line.strip():
            return line
    return ""


def parse_programme(text: str) -> TocProgramme:
    """Pull session names, paper codes and page markers out of the ToC text."""

    programme = TocProgramme()
    lines = [line.rstrip() for line in text.splitlines()]
    current_session: Optional[int] = None
    pending_letter_name: Optional[str] = None
    letter_counter = 0

    for index, line in enumerate(lines):
        bare = BARE_SESSION_RE.match(line)
        if bare:
            number = int(bare.group(1))
            # The name sits on one of the next few non-empty lines.
            name = ""
            for follow in lines[index + 1: index + 5]:
                candidate = follow.strip()
                if candidate and not CHAIR_RE.match(candidate) and len(candidate) < 90:
                    name = candidate
                    break
            programme.session_names.setdefault(number, name or f"Session {number}")
            current_session = number
            continue

        dotted = DOTTED_CODE_RE.match(line)
        if dotted:
            current_session = int(dotted.group(1))
            title = ""
            for follow in lines[index + 1: index + 4]:
                candidate = follow.strip()
                if candidate and not DOTTED_CODE_RE.match(candidate) and len(candidate) > 12:
                    title = candidate
                    break
            if title:
                programme.papers.append(TocPaper(title=title, session_number=current_session))
            continue

        numbered = NUMBERED_SESSION_RE.match(line)
        if numbered:
            number = int(numbered.group(1))
            name = numbered.group("name").strip()
            if name and len(name) < 120:
                programme.session_names.setdefault(number, name)
                current_session = number
            continue

        # ESSCIRC/ESSERC print no session codes. A session header is the line
        # directly above the "Date: / Room: / Chair(s):" block. Anchoring on
        # "Chair(s):" alone also catches the speaker name and affiliation that
        # sit above it inside plenary entries.
        if SESSION_BLOCK_RE.match(_next_nonempty(lines, index)):
            stripped = line.strip()
            if (
                stripped
                and 3 < len(stripped) < 90
                and not SESSION_BLOCK_RE.match(stripped)
                and any(
                    CHAIR_RE.match(lines[j])
                    for j in range(index + 1, min(index + 6, len(lines)))
                )
            ):
                letter_counter += 1
                name = re.sub(
                    r"^(?:PLENARY|KEYNOTE)\s*\d*\s*:\s*", "", stripped, flags=re.IGNORECASE
                ).strip()
                programme.session_names.setdefault(letter_counter, name or stripped)
                programme.header_offsets.append((index, letter_counter, name or stripped))
                current_session = letter_counter
                continue

        # RFIC-style: a "Code : Name" line, confirmed by a nearby Chair line.
        letter = LETTER_SESSION_RE.match(line)
        if letter and any(CHAIR_RE.match(lines[j]) for j in range(index + 1, min(index + 4, len(lines)))):
            letter_counter += 1
            pending_letter_name = letter.group("name").strip()
            programme.session_names.setdefault(letter_counter, pending_letter_name)
            current_session = letter_counter
            continue

        page = PAGE_MARKER_RE.match(line)
        if page and current_session is not None:
            programme.page_sessions.append((int(page.group(1)), current_session))
            continue

        code = PAPER_CODE_RE.search(line)
        if code:
            title = _clean_title(code.group("title"))
            # Titles wrap; pull in continuation lines that are not new markers.
            for follow in lines[index + 1: index + 4]:
                stripped = follow.strip()
                if not stripped or PAPER_CODE_RE.search(stripped) or stripped.startswith("»"):
                    break
                if NUMBERED_SESSION_RE.match(stripped) or PAGE_MARKER_RE.match(stripped):
                    break
                if len(stripped) < 3 or stripped[0].islower() is False and stripped.endswith(")"):
                    pass
                title += " " + stripped
            if len(title) > 12:
                programme.papers.append(
                    TocPaper(title=title.strip(), session_number=int(code.group(1)))
                )

    return programme


# ----------------------------------------------------------------------
# Applying
# ----------------------------------------------------------------------

def assign_sessions(
    year_data: Dict[str, Any],
    programme: TocProgramme,
    min_coverage: float = 0.5,
    raw_text: str = "",
    drop_unmatched: bool = False,
) -> Tuple[bool, str]:
    """
    Re-group a year's papers into the sessions the programme describes.

    Tries the page strategy and the title/code strategy, keeps whichever maps
    more papers, and refuses to apply either below min_coverage so a year is
    never given half-invented structure. Returns (applied, description).
    """

    papers = [p for s in year_data.get("sessions", []) for p in s.get("papers", [])]
    if not papers:
        return False, "no papers"

    by_page = _match_by_page(papers, programme)
    by_title = _match_by_title(papers, programme)
    by_position, position_names = ({}, {})
    if raw_text:
        by_position, position_names = match_by_position(
            papers, raw_text, extra_headers=programme.header_offsets
        )

    options = [("page", by_page), ("title", by_title), ("position", by_position)]
    strategy, mapping = max(options, key=lambda item: len(item[1]))
    if strategy == "position" and position_names:
        programme.session_names.update(
            {k: v for k, v in position_names.items() if k not in programme.session_names}
        )

    coverage = len(mapping) / len(papers)

    if drop_unmatched:
        # The programme is one track of a merged proceedings, so papers it does
        # not list belong to the other track and are meant to go. Guard on
        # absolute size instead of coverage, which is expected to be partial.
        if len(mapping) < 20 or len(set(mapping.values())) < 4:
            return False, f"only {len(mapping)} papers in {len(set(mapping.values()))} sessions; left as-is"
        papers = [p for p in papers if id(p) in mapping]
    elif coverage < min_coverage:
        return False, f"only {coverage:.0%} of papers matched ({strategy}); left as-is"

    sessions: Dict[int, Dict[str, Any]] = {}
    for paper in papers:
        number = mapping.get(id(paper))
        if number is None:
            number = 0  # unmatched papers collect in a trailing bucket
        sessions.setdefault(number, {"papers": []})["papers"].append(paper)

    ordered: List[Dict[str, Any]] = []
    for position, number in enumerate(sorted(sessions), start=1):
        name = programme.session_names.get(number) or (
            "Unassigned" if number == 0 else f"Session {number}"
        )
        entry = sessions[number]
        session = {
            "session_number": position,
            "session_code": str(number) if number else "",
            "session_name": name,
            "papers": entry["papers"],
        }
        for index, paper in enumerate(session["papers"], start=1):
            paper["session_number"] = position
            paper["session_name"] = name
            paper["paper_number"] = f"{position}.{index}"
            paper["inferred_paper_number"] = f"{position}.{index}"
        ordered.append(session)

    year_data["sessions"] = ordered
    kept = sum(len(x["papers"]) for x in ordered)
    return True, f"{strategy} strategy, {kept} papers kept, {len(ordered)} sessions"


def _match_by_page(papers: List[Dict[str, Any]], programme: TocProgramme) -> Dict[int, int]:
    if not programme.page_sessions:
        return {}
    page_to_session = dict(programme.page_sessions)
    mapping: Dict[int, int] = {}
    for paper in papers:
        page = paper.get("start_page")
        if page is None:
            continue
        try:
            page = int(page)
        except (TypeError, ValueError):
            continue
        if page in page_to_session:
            mapping[id(paper)] = page_to_session[page]
    return mapping


def _match_by_title(papers: List[Dict[str, Any]], programme: TocProgramme) -> Dict[int, int]:
    if not programme.papers:
        return {}
    # Index the programme by a prefix of the normalised title: the ToC often
    # truncates or rewraps, so a prefix compares more reliably than equality.
    index: Dict[str, int] = {}
    for entry in programme.papers:
        if entry.session_number is None:
            continue
        key = normalise(entry.title)[:40]
        if len(key) >= 20:
            index.setdefault(key, entry.session_number)

    mapping: Dict[int, int] = {}
    for paper in papers:
        key = normalise(paper.get("title", ""))[:40]
        if len(key) < 20:
            continue
        session = index.get(key)
        if session is not None:
            mapping[id(paper)] = session
    return mapping


__all__ = [
    "find_toc_records",
    "fetch_major_topics",
    "sessions_from_major_topics",
    "find_toc_record",
    "toc_pdf_url",
    "download_toc",
    "extract_text",
    "parse_programme",
    "assign_sessions",
]
