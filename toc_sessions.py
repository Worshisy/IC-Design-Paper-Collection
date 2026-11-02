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

import html
import io
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from utils import HttpError, get_session, load_json, save_json

logger = logging.getLogger(__name__)

# Front-matter titles that hold the programme, best candidate first.
# Front matter that is long but is NOT a programme - never pick these.
NON_PROGRAMME_RE = re.compile(
    r"\b(author|affiliation|subject|keyword)\s+index|^index\b|abstract\s+cards?",
    re.IGNORECASE,
)

TOC_TITLES = (
    "session list",
    "program file",
    "table of contents",
    "program",
    "advance program",
    "technical program",
    # RFIC 2006 publishes its whole programme under the bare title "Sessions";
    # RFIC 2015 as a hundred-page "Program booklet".
    "sessions",
    "program booklet",
    "programme",
    "final program",
    "conference program",
)

# "Session 12: High-speed Wireline"
NUMBERED_SESSION_RE = re.compile(
    r"^\s*(?:\d{1,2}:\d{2}\s*[ap]m\s+)?Session\s*(\d{1,3})\s*[:.–—‐‑\-]\s*(?P<name>.+?)\s*$",
    re.IGNORECASE,
)
# "5-1:" or "ES3-1:" - the session number lives in the paper's own code.
PAPER_CODE_RE = re.compile(r"\b(?:ES)?(\d{1,2})-(\d{1,3}):\s*(?P<title>.*)$")
# ESSCIRC 2002-era prints its papers "C01.01 - Title": a dot before the
# paper number and a dash before the title, where CODED_PAPER_RE expects
# "C01-01 Title". Without this every paper in the document is dropped.
CODED_PAPER_DOT_RE = re.compile(
    r"^\s*(?P<code>[A-Z]{1,4}\d{1,2}[A-Z]?)\.(?P<num>\d{1,3})\s*[-\u2013\u2014]?\s+(?P<title>\S.*)$"
)
# RFIC's printed programme: "Session RMO1B: Advances in LNA Design", with
# its papers below as "RMO1B-1 8:00 AM" and the title on the next line(s).
# The "IF" branch is RFIC's Interactive Forum, coded "RTUIF" with no digit at
# all. (?-i:IF) keeps just those two letters case-sensitive: the blanket
# IGNORECASE would otherwise let "Session Chair: Albert Jerng" match, since
# "Chair" satisfies [A-Z]{1,4} case-insensitively.
CODED_SESSION_RE = re.compile(
    r"^\s*Session\s+(?P<code>[A-Z]{1,4}\d{1,2}[A-Z]?|[A-Z]{2,4}(?-i:IF))"
    r"\s*[:.\-]\s*(?P<name>.*?)\s*$",
    re.IGNORECASE,
)
# IGNORECASE matters here too: 2022 prints its codes as "RMo1A-1". The dash and
# the meridiem are both optional - 2015 prints a bare "08:00", which without
# this leaks into the title and destroys every title match.
CODED_PAPER_RE = re.compile(
    r"^\s*(?P<code>[A-Z]{1,4}\d{1,2}[A-Z]?|[A-Z]{2,4}(?-i:IF))-?(?P<num>\d{1,3})\b\s*"
    r"(?:\d{1,2}:\d{2}\s*(?:[AP]\.?M\.?)?)?\s*(?P<title>.*)$",
    re.IGNORECASE,
)
# RFIC: "Mo1B : Advanced LC-VCO Topologies"
LETTER_SESSION_RE = re.compile(
    r"^\s*(?P<code>[A-Z][A-Za-z]{0,3}\d{1,2}[A-Z]?)\s*:\s*(?P<name>.+?)\s*$"
)
# "SESSION 1" alone on a line, with the name a line or two below (VLSI, older years).
BARE_SESSION_RE = re.compile(r"^\s*SESSION\s+(\d{1,3})\s*$", re.IGNORECASE)
# "1.1 - 8:35 a.m." - dotted code, en-dash separator (VLSI, older years).
DOTTED_CODE_RE = re.compile(r"^\s*(\d{1,2})\.(\d{1,3})\s*[\u2013\u2014-]")
OVERVIEW_PAGE_RE = re.compile(r"^\s*Session\s+O[vu]erview\b.*?(?P<page>\d{1,4})\s*$", re.IGNORECASE)
DOT_LEADER_PAGE_RE = re.compile(r"^.{6,}?\.{3,}\s*(?P<page>\d{1,4})\s*$")
PAGE_MARKER_RE = re.compile(r"^\s*Page\s+(\d{1,5})\s*$", re.IGNORECASE)
# Prefix length for the fallback title match. Long enough to be distinctive,
# short enough to sit inside a one-line title that ran on into its authors.
SHORT_TITLE_KEY = 25
# ESSCIRC heads each session "A3L-A  Analog Techniques" - the proceedings
# code, then the name. Keep them apart so the code can be displayed.
# The letter before the optional dash is REQUIRED: without it this also
# matches a VLSI paper code ("C8-3  Title"), which turned 78 of VLSI
# 2025's papers into one-paper sessions of their own.
CODE_PREFIX_RE = re.compile(
    r"^(?P<code>[A-Z]{1,2}\d{1,2}[A-Z](?:-[A-Z0-9]{1,3})?)\s{1,}(?P<name>\S.*)$"
)
# CICC heads its poster session with a bare "Poster Session" line - no
# number, no code - and codes the papers "MP-01" (2007, page after the
# code, title below) or "M-1 <title>" (2009, title on the same line).
# No colon, so PAPER_CODE_RE misses them; no digit in the code, so
# CODED_PAPER_RE does too.
POSTER_SESSION_RE = re.compile(
    r"^\s*(?:\d{1,2}:\d{2}\s*[ap]m\s*[-–—]\s*\d{1,2}:\d{2}\s*[ap]m\s+)?"
    r"(?:(?:Mon|Tues|Wednes|Thurs|Fri)day\s+)?Poster\s+Sessions?\s*$",
    re.IGNORECASE,
)
POSTER_DAY_RE = re.compile(
    r"\b(Monday|Tuesday|Wednesday|Thursday|Friday)\b", re.IGNORECASE
)
POSTER_PAPER_RE = re.compile(
    r"^\s*(?P<code>[A-Z]{1,2}P?)[-.](?P<num>\d{1,3})\s+(?P<rest>.*)$"
)
# Any real session name contains a word, and none begins with a clock time.
WORD_RE = re.compile(r"[A-Za-z]{3,}")
FRAGMENT_NAME_RE = re.compile(r"^[\s\-–—]+|^\d{1,3}\s*:")
LEADING_TIME_RE = re.compile(
    r"^[\s\-–—]*(?:\d{1,2}\s*:\s*\d{2}|\d{1,2}\s*[ap]\.?m\.?)"
)
DATE_LINE_RE = re.compile(
    r"^\s*(?:Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day\s*,", re.IGNORECASE
)
# A bare page number or a start time sitting between a paper's code and
# its title.
SCHEDULE_NOISE_RE = re.compile(r"^\d{1,3}$|^\d{1,2}\s*:\s*\d{2}\s*(?:[ap]\.?m\.?)?$", re.IGNORECASE)
LEADING_SCHEDULE_RE = re.compile(
    r"^(?:\d{1,3}\s+)?\d{1,2}\s*:\s*\d{2}\s*(?:[ap]\.?m\.?)?\s*", re.IGNORECASE
)
# CICC publishes its programme as web pages that code a paper with its
# session number, behind a start time: "10:05 am  :  2-1  :  Scaling Analog
# Circuits ...". The session number is in the code, so no surrounding
# heading is needed to place the paper.
NUMERIC_PAPER_RE = re.compile(
    r"^\s*(?:\d{1,2}\s*:\s*\d{2}\s*[ap]\.?m\.?\s*[-–—:\s]+)?"
    r"(?P<sess>\d{1,2})-(?P<num>\d{1,3})\s*[:–—]\s*(?P<title>\S.*)$",
    re.IGNORECASE,
)
# A-SSCC heads a session with no separator at all - "Session 1 Advanced
# System Integration Circuits" - and codes each paper "S-1-1(4319) Title",
# carrying the session number inside the code and the submission number in
# brackets. The capital start keeps "Session 3 continued" style noise out.
SPACED_SESSION_RE = re.compile(r"^\s*Session\s+(\d{1,3})\s+(?P<name>[A-Za-z]\S.{2,88})$")  # [c]
ASSCC_PAPER_RE = re.compile(  # [c]
    r"^\s*S-(?P<sess>\d{1,2})-(?P<num>\d{1,3})\s*(?:\(\d+\))?\s+(?P<title>\S.*)$"
)
# A-SSCC 2022 and 2023 publish an "Advance Program" instead of a ToC. The
# session number lives in the paper's own code, which sits alone on a line
# with its slot: "1.1(7033) 10:50 - 11:15" (2022) or "14-1   9:00~9:25"
# (2023, time pushed right: 3+ spaces keep ESSCIRC-style "1-1 13:45-14:10" out).
# The title follows on the next line(s).
ASSCC_ADVANCE_PAPER_RE = re.compile(
    r"^\s*(?P<sess>\d{1,2})(?:-\d{1,3}\s{3,}|\.\d{1,3}\(\d+\)\s+)"
    r"\d{1,2}:\d{2}\s*[~\u2013-]\s*\d{1,2}:\d{2}\s*$"
)
# 2022 heads a session "Session Session 6: High-Speed ADCs" above a Date: line;
# 2023 prints "14: High Precision ADCs" above a weekday line, and session 1 has
# no number at all (taken from the paper code that follows it).
ASSCC_ADVANCE_SESSION_RE = re.compile(
    r"^\s*(?:Session\s+Session\s+)?(?P<sess>\d{1,2})\s*:\s*(?P<name>[A-Z]\S.{2,100})$"
)
ASSCC_ADVANCE_DATE_RE = re.compile(r"^\s*Date\s+[A-Z][a-z]+\s+\d")  # 2022: "Date November 07, 2022 (Monday)"
# [c] A-SSCC 2020 prints "S2 Session: Low-Power Industry Solutions" above a
# "Session date and time:" line, and "S2-1 (1118) 11:10-11:35" over the title
# (one slot is typed "11;35"). The plenary talks have no id or time: skipped.
ASSCC_2020_SESSION_RE = re.compile(r"^\s*S(?P<sess>\d{1,2})\s+Session:\s*(?P<name>[A-Z]\S.{2,100})$")
ASSCC_2020_DATE_RE = re.compile(r"^\s*Session date and time:")
ASSCC_2020_PAPER_RE = re.compile(
    r"^\s*S(?P<sess>\d{1,2})-\d{1,2}\s*\(\d+\)\s+\d{1,2}[:;]\d{2}\s*[-\u2013]\s*\d{1,2}[:;]\d{2}\s*$"
)
# A-SSCC 2024's session pages (epapers2.org) print "<Name> Session" above a
# "Session Code: A1L-B" line, then each paper as paper id / topic / title /
# authors on four lines. Only a "Session Code:" line opens this mode.
WEB_SESSION_CODE_RE = re.compile(r"^\s*Session Code:\s*(?P<code>[A-Z0-9]{2,4}-?[A-Z0-9]{0,3})\s*$")  # [c]
WEB_PAPER_ID_RE = re.compile(r"^\s*\d{3,5}\s*$")  # [c]
WEB_SESSION_SUFFIX_RE = re.compile(r"\s+Session\s*$", re.IGNORECASE)  # [c]
SYNTHETIC_SESSION_BASE = 1000
# A-SSCC 2007 prints "Session Co-Chairs:" under its session header, which CHAIR_RE
# does not match, and also a schedule grid whose bare "Session 1" lines name nothing. # [c]
ASSCC_SPLIT_WORDS = {"Ampl ifiers": "Amplifiers", "Ci rcuits": "Circuits", "Re configurable": "Reconfigurable"}  # [c] 2007
# 2007 codes a paper "1-1 13:45-14:10" with ONE space, which ASSCC_ADVANCE_PAPER_RE now
# refuses (ESSCIRC prints the same shape); only trusted after a Session Co-Chairs header. # [c]
ASSCC_2007_PAPER_RE = re.compile(
    r"^\s*(?P<sess>\d{1,2})-\d{1,3} \d{1,2}:\d{2}\s*[~–-]\s*\d{1,2}:\d{2}\s*$"
)  # [c]
ASSCC_SESSION_CHAIRS_RE = re.compile(r"^\s*Session\s+Co-Chairs?\s*:", re.IGNORECASE)  # [c]
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
    session_codes: Dict[int, str] = field(default_factory=dict)
    papers: List[TocPaper] = field(default_factory=list)
    page_sessions: List[Tuple[int, int]] = field(default_factory=list)  # (page, session)
    header_offsets: List[Tuple[int, int, str]] = field(default_factory=list)  # (line, number, name)
    explicit_codes: bool = False  # [c] papers carry their session number (A-SSCC Advance Program)


# ----------------------------------------------------------------------
# Fetching
# ----------------------------------------------------------------------

_ROMAN_RE = re.compile(r"^[ivxlcdm]+$", re.IGNORECASE)
_ROMAN_VALUES = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}


_COVER_PAGE_RE = re.compile(r"^[cC](\d+)$")  # [c]


def _roman_to_int(text: str) -> Optional[int]:
    total, previous = 0, 0
    for char in reversed(text.lower()):
        value = _ROMAN_VALUES.get(char)
        if value is None:
            return None
        if value < previous:
            total -= value
        else:
            total += value
            previous = value
    return total


def _page_value(raw: Any) -> Optional[int]:
    """A page number as an int - front matter is often paginated "i".."xcii"."""

    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        pass
    # Cover-section pagination: "c1".."c30". The C is the section letter, not a
    # roman hundred, so this has to be tried first. A-SSCC 2025 files its whole
    # 30-page programme under the title "A-SSCC 2025 Cover Page", and without
    # this its span reads 0 and it is never considered.
    cover = _COVER_PAGE_RE.match(text)  # [c]
    if cover:
        return int(cover.group(1))
    return _roman_to_int(text) if _ROMAN_RE.match(text) else None


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
        start = _page_value(record.get("startPage"))
        end = _page_value(record.get("endPage"))
        if start is None or end is None:
            return 0
        return end - start

    candidates: List[Tuple[int, Dict[str, Any]]] = []
    for record in records:
        title = (record.get("articleTitle") or "").strip().lower()
        abstract = (record.get("abstract") or "").strip().lower()
        span = span_of(record)
        if NON_PROGRAMME_RE.search(title) or span > 200:
            continue

        # "ESSCIRC 2023 Table of Contents" should count; a paper titled
        # "Programmable ..." should not, hence the letter boundaries.
        named = any(
            re.search(rf"(?<![a-z]){re.escape(phrase)}(?![a-z])", title)
            for phrase in TOC_TITLES
        )
        # IEEE describes the document in the abstract even when the title does
        # not say so, and older records often have no endPage at all, so the
        # size test alone misses them: ISSCC 2000/2001 ship their table of
        # contents as "<year> IEEE International Solid-State Circuits
        # Conference [Front Matter and Table of Contents]" with endPage unset.
        # IEEE gives a whole-proceedings record - the printed digest, which
        # carries the programme - an abstract that lists the conference's
        # topics. ISSCC 2003's digest has no page range and a title that names
        # only the conference, so this phrase is the only thing marking it.
        declared = (
            "table of contents" in abstract
            or "front matter" in abstract
            or (
                # IEEE also uses this opener for the auto-generated keyword
                # abstract of an ordinary paper, so require no authors: a
                # whole-proceedings record has none, a real paper does.
                abstract.startswith("the following topics are dealt with")
                and not record.get("authors")
            )
        )
        if not (named or declared) and (span < 8 or record.get("authors")):
            continue
        # Declared tables of contents outrank size-based guesses.
        candidates.append((-10_000 if declared and not named else -span, record))

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
        printed = re.match(r"\s*Session\s+(\d+)", heading, re.IGNORECASE)
        session = {
            "session_number": position,
            "session_code": printed.group(1) if printed else str(position),
            "session_name": name,
            "papers": grouped[heading],
        }
        # Number papers after the printed session code, so "Session 30" holds
        # 30.1, 30.2 ... rather than a positional counter the reader cannot see.
        prefix = session["session_code"] or str(position)
        for index, paper in enumerate(session["papers"], start=1):
            paper["session_number"] = position
            paper["session_name"] = name
            paper["paper_number"] = f"{prefix}.{index}"
            paper["inferred_paper_number"] = f"{prefix}.{index}"
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
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
        return _unshift_title_lines(_unshift_glyphs(text))  # [c]
    except Exception as exc:
        logger.warning("Could not read the programme PDF: %s", exc)
        return ""


# ----------------------------------------------------------------------
# Parsing
# ----------------------------------------------------------------------

def respace(text: str) -> str:
    """
    Put spaces back into run-together PDF text.

    Some older programme PDFs extract with every space stripped, so a session
    reads "ImageSensors&Technology". Splitting on lower->upper transitions and
    around digits restores something readable without touching text that
    already has spaces.
    """

    if not text or " " in text.strip():
        return text
    spaced = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
    spaced = re.sub(r"(?<=[A-Za-z])(?=\d)|(?<=\d)(?=[A-Za-z])", " ", spaced)
    spaced = re.sub(r"\s*&\s*", " & ", spaced)
    return re.sub(r"\s{2,}", " ", spaced).strip()


def _clean_title(text: str) -> str:
    return TITLE_NOISE_RE.sub("", text or "").strip()


# LaTeX wrappers that carry no visible text: the programme PDF prints the
# rendered form ("VO2"), while the stored title holds the source
# ("$\text{VO}_{2}$"). Strip the macro names so both normalise alike.
_LATEX_MACRO_RE = re.compile(r"\\(?:text|mathrm|mathbf|mathit|boldsymbol|hbox|mbox|rm|bf|it)\b")
_LATEX_LEFTOVER_RE = re.compile(r"\\[A-Za-z]+")


def normalise(title: str) -> str:
    """
    Comparison key: lowercase alphanumerics, with LaTeX source neutralised.

    Without this, a title like "$\text{VO}_{2}$ Based Negative..." keys as
    "textvo2based..." and never matches the programme's "VO2 Based ...",
    which stranded 40 of ESSCIRC 2025's papers as Unassigned.
    """

    text = title or ""
    text = _LATEX_MACRO_RE.sub(" ", text)
    text = _LATEX_LEFTOVER_RE.sub(" ", text)
    # Keep non-ASCII letters rather than dropping them: VLSI titles are full of
    # uW, Delta-Sigma, Ohm and superscripts, and the search haystack built by
    # _normalised_with_map keeps them, so stripping here desynced the two by a
    # character and broke every match that crossed one. NFKC first, because the
    # API and the PDF disagree on confusables - MICRO SIGN U+00B5 against GREEK
    # SMALL LETTER MU U+03BC - which fold to the same character.
    text = unicodedata.normalize("NFKC", text)
    return "".join(ch.lower() for ch in text if ch.isalnum())


def _normalised_with_map(text: str) -> Tuple[str, List[int]]:
    """Lowercase alphanumeric text plus a map back to original offsets."""

    chars: List[str] = []
    offsets: List[int] = []
    for index, char in enumerate(text):
        # Fold per character, never the whole string: NFKC can expand a
        # ligature or fraction into several characters, which would slide
        # every later offset away from the original text that the heading
        # lookup in match_by_position indexes into.
        for folded in unicodedata.normalize("NFKC", char):
            if folded.isalnum():
                chars.append(folded.lower())
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
    pattern = (r"Session\s*(\d{1,3})\s*[-:.–—‐‑]\s*([^\n]{3,90})"
               r"|SESSION\s*(\d{1,3})\s*\n\s*\n?\s*([^\n]{3,90})")
    for match in re.finditer(pattern, text, re.IGNORECASE):
        number = match.group(1) or match.group(3)
        name = _session_name((match.group(2) or match.group(4) or "").strip())
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


# Lines that are clearly not session topics. ESSCIRC's programme puts author
# affiliations and keynote speaker names in the same position as a heading.
AFFILIATION_NAME_RE = re.compile(
    r"(?:univers|instit|laborator|technolog(?:y|ies)\s*,|gmbh|inc\.|ltd|corporation|"
    r"semiconductor|research\s+cent|academy|college|\bAG\b|\bBV\b|\bSA\b)",
    re.IGNORECASE,
)
# "Firstname Lastname" and nothing else - a speaker, not a topic.
# Session-slot fillers that sit where a real header sits - directly above a
# "Date:/Room:/Chair(s)" block - but hold no papers. A "looks like Firstname
# Lastname" heuristic used to guard this, but the same two-Title-Case-word
# shape is an ordinary session topic ("Power Converters", "Compact Modeling",
# "Cryptographic Accelerators"). It merged 35 real ESSCIRC/ESSERC sessions
# into whichever session preceded them, and only ever correctly caught
# "Coffee Break".
NON_SESSION_FILLER_RE = re.compile(
    r"^(?:coffee|lunch)\s+break$|^(?:welcome|farewell)\s+reception$|"
    r"^networking\s+(?:break|reception|lunch)$",
    re.IGNORECASE,
)

PERSON_NAME_RE = re.compile(r"^[A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-zA-Z'\-]+$")
# Trailing ", Country" is the giveaway for an affiliation line.
COUNTRY_TAIL_RE = re.compile(r",\s*(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*$")


def is_plausible_session_name(name: str) -> bool:
    """Reject affiliations, bare person names and numeric noise."""

    text = (name or "").strip()
    if len(text) < 4 or len(text) > 110:
        return False
    if text[0].isdigit() and COUNTRY_TAIL_RE.search(text):
        return False          # "4Katholieke Universiteit Leuven, Belgium"
    if AFFILIATION_NAME_RE.search(text) and COUNTRY_TAIL_RE.search(text):
        return False
    if NON_SESSION_FILLER_RE.match(text):
        return False          # "Coffee Break"
    if FRAGMENT_NAME_RE.match(text):
        # A leading dash or "12:" is the tail of a wrapped heading, not a name.
        # CICC 2015 ended up with a session called "- Low power analog" holding
        # 104 of its 123 papers, and 2018 with "2: Time interleaved ADCs r"
        # holding 107 of 109.
        return False
    if LEADING_TIME_RE.match(text):
        # "- 9:25 (Plenary)": the programme prints a time before each entry, and
        # taking that line as a heading splits a real session into fragments.
        # A word elsewhere in the line is not enough to rescue it.
        return False
    if not WORD_RE.search(text):
        # "- 16:25" and friends: VLSI 2017/2019 print a time after each paper,
        # and taking those as headings split real sessions into one-paper
        # fragments - 111 of 2017's 116 "sessions" held a single paper.
        return False
    return True


def _next_nonempty(lines: List[str], index: int) -> str:
    for line in lines[index + 1: index + 4]:
        if line.strip():
            return line
    return ""


_GLYPH_SHIFT = 29
NEWLINES = (chr(10), chr(13))


def _unshift_glyphs(text: str) -> str:
    """
    Undo the fixed glyph-code offset some ESSCIRC programme PDFs extract with.

    Their embedded font maps each character 29 codepoints below the ASCII it
    prints, so "ESSCIRC Table of Contents" comes out as "(66&,5&7DEOHRI...".
    In that mapping the word space shifts to "=", which is put back\\". Line breaks are
    structure from the extractor, not glyphs, so they are left alone.

    Applied only when shifting actually produces recognisable words, so a
    normally-encoded document is never touched.
    """

    if "Session" in text or "Table of Contents" in text:
        return text

    top = 0x7E - _GLYPH_SHIFT
    shifted = "".join(
        ch if ch in NEWLINES or not (0x03 <= ord(ch) <= top) else chr(ord(ch) + _GLYPH_SHIFT)
        for ch in text
    )
    markers = ("Session", "Table of Contents", "University", "Date", "Room")
    if sum(marker in shifted for marker in markers) >= 2:
        # A real colon decodes on its own; "=" is the shifted word space.
        return shifted.replace("=", " ")
    return text


# [c] A-SSCC 2014 prints every paper title (and some page numbers) in a font
# whose codes sit 29 below ASCII, but only those: names and affiliations are
# plain. The leader before the page is a run of U+00B7 or U+0101, which
# DOT_LEADER_PAGE_RE does not accept, so it is rewritten to dots here.
_TITLE_LEADER_RE = re.compile("[\x01\x03]*[\u00b7\u0101]{3,}")
_TITLE_PLAIN_PREFIX_RE = re.compile(r"(?:Industry\s+)?\d{1,2}-\d{1,2}\s+")
_TITLE_INDUSTRY_RE = re.compile(r"^\s*Industry Session (\d{1,2})\s*$")
_TITLE_SPECIAL_GLYPHS = {"\u00bf": "fi", "\u0083": "\u00b0", "\u021d": "\u00b5"}


def _unshift_title_lines(text: str) -> str:
    """
    Undo the glyph shift on the title lines of A-SSCC 2014's programme.

    A shifted title line is told from a plain one by the shifted word space
    (U+0003); plain text never contains it before the leader. The paper code
    ("Industry 2-1") is sometimes plain, so it is kept. "Industry Session 02"
    becomes a bare "Session 02" with "Industry Session:" ahead of its name.
    Extracting also leaves
    U+001C - the shifted digit 9 - which splitlines() treats as a line break,
    so this runs on the whole text before anything splits it.
    """

    lines = text.split("\n")
    if sum("\x03" in line for line in lines) < 20:
        return text

    def unshift(chars: str) -> str:
        return "".join(
            chr(ord(ch) + _GLYPH_SHIFT) if 0x03 <= ord(ch) <= 0x7E - _GLYPH_SHIFT and ch != " " else ch
            for ch in chars
        )

    fixed: List[str] = []
    label_next = False
    for line in lines:
        line = line.rstrip("\r")
        industry = _TITLE_INDUSTRY_RE.match(line)
        if industry:
            fixed.append("Session " + industry.group(1))
            label_next = True
            continue
        if label_next and line.strip():
            line = "Industry Session: " + line
            label_next = False
        leader = _TITLE_LEADER_RE.search(line)
        body, tail = (line[:leader.start()], line[leader.end():]) if leader else (line, "")
        if "\x03" in body.rstrip("\x03"):
            prefix = _TITLE_PLAIN_PREFIX_RE.match(body)
            split = prefix.end() if prefix else 0
            body = body[:split] + unshift(body[split:])
            for glyph, replacement in _TITLE_SPECIAL_GLYPHS.items():
                body = body.replace(glyph, replacement)
        if leader:
            body += "..... "
            tail = "".join(chr(ord(ch) + _GLYPH_SHIFT) if ord(ch) < 0x20 else ch for ch in tail)
        fixed.append(body + tail)
    return "\n".join(fixed)


LEADING_SEPARATOR_RE = re.compile(r"^[\s:\-–—]+")


def _session_name(text: str) -> str:
    """
    Respace a captured session name and drop any separator left in front of it.

    "Session 2 - Low power analog" hands back "- Low power analog" from several
    of the header patterns, and that leading dash then fails every plausibility
    check downstream - CICC 2015 ended up with one session holding 104 of its
    123 papers because of it.
    """

    return LEADING_SEPARATOR_RE.sub("", respace(text)).strip()


def parse_programme(text: str) -> TocProgramme:
    """Pull session names, paper codes and page markers out of the ToC text."""

    programme = TocProgramme()
    lines = [line.rstrip() for line in text.splitlines()]
    current_session: Optional[int] = None
    pending_letter_name: Optional[str] = None
    # Synthetic sessions (poster blocks, code-prefixed headers) are numbered
    # from here. It must not overlap the numbers real "Session N" headings use,
    # or their papers merge: CICC 2015's poster papers were landing in sessions
    # 4 and 6 because the poster block had been allocated number 4.
    letter_counter = SYNTHETIC_SESSION_BASE
    coded_sessions: Dict[str, int] = {}   # "RMO1B" -> synthetic session number
    poster_active = False                 # inside a bare "Poster Session" block
    chairs_seen = False                   # [c] a 2007-style "Session Co-Chairs:" header was met
    poster_session: Optional[int] = None  # the session that block opened
    web_session_active = False            # inside an epapers2 "Session Code:" page
    consumed: set = set()                 # title lines already taken as papers

    for index, line in enumerate(lines):
        if index in consumed:
            continue

        # A-SSCC 2024 web pages: the name is the "... Session" line above the code.
        web_code = WEB_SESSION_CODE_RE.match(line)  # [c]
        if web_code:
            above = [ln.strip() for ln in lines[max(0, index - 6): index] if ln.strip()]
            heading = above[-2] if len(above) >= 2 else ""
            if above[-1].startswith("Session Type:") and WEB_SESSION_SUFFIX_RE.search(heading):
                name = _session_name(WEB_SESSION_SUFFIX_RE.sub("", heading).strip())
                if name and len(name) < 120 and is_plausible_session_name(name):
                    letter_counter += 1
                    programme.session_names.setdefault(letter_counter, name)
                    programme.session_codes.setdefault(letter_counter, web_code.group("code").upper())
                    poster_active = False
                    web_session_active = True
                    current_session = letter_counter
            continue
        if web_session_active and WEB_PAPER_ID_RE.match(line):  # [c]
            ahead = [j for j in range(index + 1, min(index + 4, len(lines))) if lines[j].strip()]
            if len(ahead) >= 2 and lines[ahead[0]].strip().isdigit():
                title = respace(lines[ahead[1]].strip())
                if len(title) > 15:
                    programme.papers.append(TocPaper(title=title, session_number=current_session))
                    consumed.add(ahead[1])
                continue

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
            poster_active = False
            continue

        if POSTER_SESSION_RE.match(line):
            letter_counter += 1
            day = ""
            for follow in lines[index + 1: index + 4]:
                found = POSTER_DAY_RE.search(follow)
                if found:
                    day = found.group(1).title()
                    break
            name = f"Poster Session ({day})" if day else "Poster Session"
            programme.session_names.setdefault(letter_counter, name)
            programme.header_offsets.append((index, letter_counter, name))
            current_session = letter_counter
            poster_session = letter_counter
            poster_active = True
            continue

        numeric_paper = NUMERIC_PAPER_RE.match(line)
        if numeric_paper:
            title = respace(numeric_paper.group("title").strip())
            if len(title) > 15:
                programme.papers.append(
                    TocPaper(title=title, session_number=int(numeric_paper.group("sess")))
                )
                continue

        # [c] A-SSCC 2022/2023 Advance Program (see ASSCC_ADVANCE_*_RE).
        advance_paper = ASSCC_ADVANCE_PAPER_RE.match(line) or ASSCC_2020_PAPER_RE.match(line) or (  # [c] 2020
            chairs_seen and ASSCC_2007_PAPER_RE.match(line)  # [c]
        )
        if advance_paper:
            parts = []
            for follow in lines[index + 1: index + 4]:
                candidate = follow.strip()
                if (
                    not candidate
                    or candidate.startswith("-")
                    or ASSCC_ADVANCE_PAPER_RE.match(candidate)
                    or len(" ".join(parts)) > 60
                ):
                    break
                parts.append(candidate)
            title = respace(" ".join(parts).strip())
            if len(title) > 15:
                programme.papers.append(
                    TocPaper(title=title, session_number=int(advance_paper.group("sess")))
                )
            current_session = int(advance_paper.group("sess"))
            programme.explicit_codes = True
            continue

        # [c] A-SSCC 2020: the name may wrap onto a second line before the date line.
        session_2020 = ASSCC_2020_SESSION_RE.match(line)
        if session_2020:
            name_text = session_2020.group("name").strip()
            after = _next_nonempty(lines, index)
            if not ASSCC_2020_DATE_RE.match(after) and ASSCC_2020_DATE_RE.match(
                _next_nonempty(lines, index + 1)
            ):
                name_text += " " + after.strip()
            elif not ASSCC_2020_DATE_RE.match(after):
                name_text = ""
            number = int(session_2020.group("sess"))
            name = _session_name(name_text) if name_text else ""
            if name and is_plausible_session_name(name):
                programme.session_names.setdefault(number, name)
                programme.session_codes.setdefault(number, str(number))
                current_session = number
                poster_active = False
                continue

        advance_session = ASSCC_ADVANCE_SESSION_RE.match(line)
        if advance_session:
            after = _next_nonempty(lines, index)
            if ASSCC_ADVANCE_DATE_RE.match(after) or DATE_LINE_RE.match(after):
                number = int(advance_session.group("sess"))
                name = _session_name(advance_session.group("name").strip())
                if name and is_plausible_session_name(name):
                    programme.session_names.setdefault(number, name)
                    programme.session_codes.setdefault(number, str(number))
                    current_session = number
                    poster_active = False
                continue

        # 2023: an unnumbered header (session 1) is a name above a weekday line,
        # directly after the "Session Co-Chair" label, with a paper code close
        # below that carries the number.
        if (
            index > 0
            and lines[index - 1].strip() == "Session Co-Chair"
            and DATE_LINE_RE.match(_next_nonempty(lines, index))
        ):
            for follow in lines[index + 1: index + 9]:
                found = ASSCC_ADVANCE_PAPER_RE.match(follow)
                if found:
                    name = _session_name(line.strip())
                    if name and is_plausible_session_name(name):
                        number = int(found.group("sess"))
                        programme.session_names.setdefault(number, name)
                        programme.session_codes.setdefault(number, str(number))
                    break

        asscc_paper = ASSCC_PAPER_RE.match(line)  # [c]
        if asscc_paper:
            session_number = int(asscc_paper.group("sess"))
            # The title wraps onto the following lines and ends at a dotted
            # leader holding the page number. 60 characters is more than the
            # title matcher keys on, so stopping there keeps the author block
            # that follows out of the key.
            parts = [asscc_paper.group("title").strip()]
            for follow in lines[index + 1: index + 4]:
                candidate = follow.strip()
                if (
                    not candidate
                    or candidate.startswith("-")
                    or ASSCC_PAPER_RE.match(candidate)
                    or len(" ".join(parts)) > 60
                ):
                    break
                parts.append(candidate)
            title = respace(" ".join(parts).strip())
            if len(title) > 15:
                programme.papers.append(
                    TocPaper(title=title, session_number=session_number)
                )
            current_session = session_number
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

        poster_paper = POSTER_PAPER_RE.match(line) if poster_active else None
        if poster_paper and current_session is not None:
            remainder = poster_paper.group("rest").strip()
            if remainder and not remainder.isdigit() and len(remainder) > 12:
                title = remainder                 # 2009: title on the code's line
            else:
                title = ""                        # 2007: code + page, title below
                for follow in lines[index + 1: index + 4]:
                    candidate = follow.strip()
                    if not candidate:
                        continue
                    if POSTER_PAPER_RE.match(candidate):
                        break
                    title = (title + " " + candidate).strip() if title else candidate
                    if len(title) > 60:
                        break
            title = LEADING_SEPARATOR_RE.sub("", title).strip()
            if len(title) > 12:
                programme.papers.append(
                    TocPaper(
                        title=title,
                        session_number=poster_session if poster_session is not None else current_session,
                    )
                )
            continue

        coded = CODED_SESSION_RE.match(line)
        if coded:
            code = coded.group("code").upper()
            name = _session_name(coded.group("name").strip())
            if not name:
                # "Session RMo2A:" with the title wrapped onto the next line.
                # RFIC 2019 does this for every title too long to fit, which
                # dropped 9 of its 20 sessions.
                follow = _next_nonempty(lines, index).strip()
                if follow and len(follow) < 120 and is_plausible_session_name(follow):
                    name = _session_name(follow)
            if name and len(name) < 120:
                letter_counter += 1
                programme.session_names.setdefault(letter_counter, name)
                programme.session_codes.setdefault(letter_counter, code)
                coded_sessions[code] = letter_counter
                poster_active = False
                current_session = letter_counter
            continue

        # The dot form is tried first: CODED_PAPER_RE also matches "C01.01" but
        # mis-reads it as code "C0", paper 1, which then fails the session
        # lookup and silently drops the paper.
        coded_paper = CODED_PAPER_DOT_RE.match(line) or CODED_PAPER_RE.match(line)
        if coded_paper and coded_paper.group("code").upper() in coded_sessions:
            session_number = coded_sessions[coded_paper.group("code").upper()]
            # The title follows on its own line(s), wrapped by the PDF. Two
            # lines are plenty for the 40-character prefix the title matcher
            # keys on, and stopping at the next code keeps entries separate.
            # The same "<page> <time>" noise often sits on the code's own line,
            # inside the captured title group.
            parts = [LEADING_SCHEDULE_RE.sub("", coded_paper.group("title").strip()).strip()]
            # RFIC 2019 puts the code on its own line and the title three lines
            # later, behind a stray page number and a start time:
            #   RMo1A-1 / " 0" / "8:00" / "A 1.2-2.8GHz Tunable Low-Noise ..."
            # Letting those into the key destroys the title prefix the matcher
            # compares on, so skip them rather than stopping.
            for follow in lines[index + 1: index + 7]:
                candidate = follow.strip()
                if not candidate or SCHEDULE_NOISE_RE.match(candidate):
                    continue
                # The same noise also arrives inline: "0 8:20 A 28-GHz CMOS LNA".
                candidate = LEADING_SCHEDULE_RE.sub("", candidate).strip()
                if not candidate:
                    continue
                if CODED_PAPER_RE.match(candidate) or CODED_SESSION_RE.match(candidate):
                    break
                parts.append(candidate)
                if len(" ".join(parts)) > 60:
                    break
            title = respace(" ".join(part for part in parts if part).strip())
            if len(title) > 15:
                programme.papers.append(TocPaper(title=title, session_number=session_number))
            current_session = session_number
            continue

        numbered = NUMBERED_SESSION_RE.match(line)
        chaired_header = False  # [c]
        confirmed_header = False  # [c]
        if not numbered:
            # A-SSCC's separator-less header. The chairs line under it is what
            # separates a real header from a schedule grid ("Session 11 Session
            # 12 Session 13") or a contents line ending in page numbers, both
            # of which this shape otherwise matches.
            spaced = SPACED_SESSION_RE.match(line)  # [c]
            if spaced and any(
                CHAIR_RE.match(lines[j])
                for j in range(index + 1, min(index + 4, len(lines)))
            ):
                numbered = spaced
                chaired_header = True  # [c]
            # [c] 2007: confirmed by "Session Co-Chairs:", and it replaces the
            # grid's truncated name ("Power Efficient Circuits and").
            elif spaced and any(
                ASSCC_SESSION_CHAIRS_RE.match(lines[j])
                for j in range(index + 1, min(index + 4, len(lines)))
            ):
                numbered = spaced
                confirmed_header = True
                chairs_seen = True  # [c]
        if numbered:
            number = int(numbered.group(1))
            name = numbered.group("name").strip()
            name = _session_name(name)

            # VLSI heads a session with its room ("Session 2 - TAPA 1") and puts
            # the topic on the next line, above the date. Without this every
            # session is named after a meeting room, and rooms repeat.
            follow = [
                (offset, lines[offset].strip())
                for offset in range(index + 1, min(index + 4, len(lines)))
                if lines[offset].strip()
            ]
            # ...but A-SSCC prints "Chair: ..." there, above its own date line,
            # which would name every session after its chairs.
            if (
                len(follow) >= 2
                and DATE_LINE_RE.match(follow[1][1])
                and not CHAIR_RE.match(follow[0][1])  # [c]
            ):
                candidate = _session_name(follow[0][1])
                if candidate and len(candidate) < 120 and is_plausible_session_name(candidate):
                    name = candidate

            if name and len(name) < 120 and is_plausible_session_name(name):
                if confirmed_header:  # [c]
                    # The PDF's font splits some words: "Ampl ifiers", "Ci rcuits".
                    for split, joined in ASSCC_SPLIT_WORDS.items():
                        name = name.replace(split, joined)
                    programme.session_names[number] = name
                programme.session_names.setdefault(number, name)
                programme.session_codes.setdefault(number, str(number))
                if chaired_header:  # [c]
                    # A-SSCC 2013: titles carry no codes, so position matching
                    # needs this header's offset (and "mmWave ..." is lower-case).
                    programme.header_offsets.append((index, number, name))
                poster_active = False
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
                # ESSCIRC 2007 prints no "Chair" line anywhere in its
                # programme, only Time:/Place: blocks. A code prefix is itself
                # strong enough evidence of a heading.
                and (
                    any(
                        CHAIR_RE.match(lines[j])
                        for j in range(index + 1, min(index + 6, len(lines)))
                    )
                    or CODE_PREFIX_RE.match(stripped)
                )
            ):
                plenary = re.match(
                    r"^((?:PLENARY|KEYNOTE)\s*\d*)\s*:\s*(.*)$", stripped, re.IGNORECASE
                )
                if plenary:
                    # "PLENARY 1: Marc Biron" - the session is the plenary, not
                    # the speaker, so keep the label rather than the name.
                    name = plenary.group(1).strip().title()
                elif is_plausible_session_name(stripped):
                    name = stripped
                else:
                    continue

                letter_counter += 1
                prefixed = CODE_PREFIX_RE.match(name)
                if prefixed:
                    programme.session_codes.setdefault(
                        letter_counter, prefixed.group("code").upper()
                    )
                    name = prefixed.group("name").strip()
                programme.session_names.setdefault(letter_counter, name)
                programme.header_offsets.append((index, letter_counter, name))
                current_session = letter_counter
                continue

        # ESSCIRC 2009 prints "A2L-A  Joint Session - ..." with no Date/Room/
        # Chair block at all: the next line is the first paper's title.
        bare_code = CODE_PREFIX_RE.match(line.strip())
        if (
            bare_code
            and not DOT_LEADER_PAGE_RE.match(line)
            and is_plausible_session_name(bare_code.group("name"))
        ):
            letter_counter += 1
            programme.session_codes.setdefault(letter_counter, bare_code.group("code").upper())
            name = bare_code.group("name").strip()
            programme.session_names.setdefault(letter_counter, name)
            programme.header_offsets.append((index, letter_counter, name))
            current_session = letter_counter
            poster_active = False
            continue

        # RFIC-style: a "Code : Name" line, confirmed by a nearby Chair line.
        letter = LETTER_SESSION_RE.match(line)
        if letter and any(CHAIR_RE.match(lines[j]) for j in range(index + 1, min(index + 4, len(lines)))):
            letter_counter += 1
            pending_letter_name = letter.group("name").strip()
            programme.session_names.setdefault(letter_counter, pending_letter_name)
            # "Mo1B" is what the proceedings prints; keep it for display.
            programme.session_codes.setdefault(letter_counter, letter.group("code").upper())
            poster_active = False
            current_session = letter_counter
            continue

        page = PAGE_MARKER_RE.match(line)
        if page and current_session is not None:
            programme.page_sessions.append((int(page.group(1)), current_session))
            continue

        # "1.2 Surface and Tangible Computing ............ 24" - the trailing
        # number is the printed page. Gives page markers for programmes that
        # have no standalone "Page N" lines (older ISSCC tables of contents).
        overview_page = OVERVIEW_PAGE_RE.match(line)
        if overview_page and current_session is not None:
            programme.page_sessions.append((int(overview_page.group("page")), current_session))
            continue

        dotted_page = DOT_LEADER_PAGE_RE.match(line)
        if dotted_page and current_session is not None:
            programme.page_sessions.append((int(dotted_page.group("page")), current_session))
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

    # Count alone is the wrong score. VLSI 2026's own programme maps 137 papers
    # by position but into 3 buckets, while title matching maps 136 into 25 real
    # sessions - the first wins on count and is then thrown out by the
    # degenerate-grouping guard below, losing the year entirely. Require the
    # same spread the guard demands before a strategy is eligible.
    eligible = [item for item in options if len(set(item[1].values())) >= 4]
    if not eligible or len(papers) <= 30:
        eligible = options
    strategy, mapping = max(eligible, key=lambda item: len(item[1]))
    # [c] A-SSCC 2022 re-prints every FPGA demo title outside its session, so
    # reading position outscored the printed paper codes and filed 23 papers
    # under one session. A code names the session outright: trust it.
    if programme.explicit_codes and by_title and ("title", by_title) in eligible:
        strategy, mapping = "title", by_title
    if strategy == "position" and position_names:
        # match_by_position has its own heading regex, so its names never went
        # through the plausibility check: "Poster Session 5:00 pm - 7:00 pm"
        # arrived as session 5 named "00 pm - 7:00 pm".
        programme.session_names.update({
            k: v for k, v in position_names.items()
            if k not in programme.session_names and is_plausible_session_name(v)
        })

    # Fill the winner's gaps from the other strategy. Page and title matching
    # both key on the programme's own session numbers, so their answers are
    # interchangeable; position matching numbers headers it found in the raw
    # text, so it is only ever used alone.
    if strategy in ("page", "title"):
        fallback = by_title if strategy == "page" else by_page
        mapping = dict(mapping)
        for key, number in fallback.items():
            mapping.setdefault(key, number)

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
    elif len(papers) > 30 and len(set(mapping.values())) < 4:
        # Coverage can clear the bar while the papers all land in one or two
        # buckets - a programme whose headers were mostly missed. That is worse
        # than the single "General" session it would replace, because it also
        # invents an Unassigned pile. ESSCIRC 2003 did exactly this: 58% of
        # 175 papers into one session, 74 unassigned.
        return False, (
            f"{coverage:.0%} matched but only {len(set(mapping.values()))} "
            f"session(s) ({strategy}); left as-is"
        )

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
            "session_code": programme.session_codes.get(number) or (
                "" if number >= SYNTHETIC_SESSION_BASE else (str(number) if number else "")
            ),
            "session_name": name,
            "papers": entry["papers"],
        }
        # Number papers after the printed session code so the header and the
        # rows agree; fall back to the position only when there is no code.
        prefix = session["session_code"] or str(position)
        for index, paper in enumerate(session["papers"], start=1):
            paper["session_number"] = position
            paper["session_name"] = name
            paper["paper_number"] = f"{prefix}.{index}"
            paper["inferred_paper_number"] = f"{prefix}.{index}"
        ordered.append(session)

    year_data["sessions"] = ordered
    kept = sum(len(x["papers"]) for x in ordered)
    return True, f"{strategy} strategy, {kept} papers kept, {len(ordered)} sessions"


def _match_by_page(papers: List[Dict[str, Any]], programme: TocProgramme) -> Dict[int, int]:
    """
    Assign papers to sessions by printed page.

    Matched by RANGE, not by exact page. The programme lists one marker per
    paper it knows about, but a paper added late - or one the marker list
    simply misses - still sits physically inside its session's page span.
    Requiring an exact hit stranded real papers in "Unassigned" (RFIC 2026
    lost five that way, all with full author lists).
    """

    if not programme.page_sessions:
        return {}

    # Only markers whose session actually has a name. A programme can carry a
    # header that numbers as 0 with no title; papers landing on it rendered as
    # "Unassigned" even though they sit inside a perfectly good session, so
    # fall through to the nearest NAMED session instead.
    named = set(programme.session_names)
    markers = sorted({(page, number) for page, number in programme.page_sessions
                      if number in named})
    if not markers:
        markers = sorted(set(programme.page_sessions))
    pages = [page for page, _ in markers]

    import bisect

    mapping: Dict[int, int] = {}
    for paper in papers:
        raw = paper.get("start_page")
        try:
            page = int(raw)
        except (TypeError, ValueError):
            continue
        index = bisect.bisect_right(pages, page) - 1
        if index >= 0:
            mapping[id(paper)] = markers[index][1]
    return mapping


def _match_by_title(papers: List[Dict[str, Any]], programme: TocProgramme) -> Dict[int, int]:
    if not programme.papers:
        return {}
    # Index the programme by a prefix of the normalised title: the ToC often
    # truncates or rewraps, so a prefix compares more reliably than equality.
    index: Dict[str, int] = {}
    # A title shorter than the wrap width runs on into the author line, so its
    # 40-character key carries author text the real title never has. Index a
    # shorter prefix too, and use it only where it names exactly one session.
    short_index: Dict[str, Set[int]] = {}
    for entry in programme.papers:
        if entry.session_number is None:
            continue
        normalised = normalise(entry.title)
        key = normalised[:40]
        if len(key) >= 20:
            index.setdefault(key, entry.session_number)
        short = normalised[:SHORT_TITLE_KEY]
        if len(short) >= SHORT_TITLE_KEY:
            short_index.setdefault(short, set()).add(entry.session_number)

    mapping: Dict[int, int] = {}
    for paper in papers:
        normalised = normalise(paper.get("title", ""))
        if len(normalised) < 20:
            continue
        session = index.get(normalised[:40])
        if session is None:
            candidates = short_index.get(normalised[:SHORT_TITLE_KEY])
            if candidates and len(candidates) == 1:
                session = next(iter(candidates))
        if session is not None:
            mapping[id(paper)] = session
    return mapping



def drop_session_overview_records(year_data: Dict[str, Any]) -> int:
    """
    Remove the chairs' session-introduction records, which IEEE files as papers.

    Their title is the session's own name, differing only in case ("Radio
    receiver techniques" against the session "Radio Receiver Techniques"), so
    they are recognisable without reading the abstract. They are worth removing
    for their own sake and because they inflate a session's paper count.

    The guard matters: a session that holds a single paper is sometimes *named*
    after that paper, and dropping it would delete real work. Requiring the
    matching session to hold at least two other papers separates the two cases
    - measured across the corpus it spares exactly the real papers and removes
    only overview records.

    Returns the number of records removed.
    """

    sessions = year_data.get("sessions", [])
    if not sessions:
        return 0

    by_name = {
        session["session_name"].strip().lower(): session
        for session in sessions
        if session.get("session_name") not in ("Unassigned", "General")
    }

    removed = 0
    for session in sessions:
        kept = []
        for paper in session.get("papers", []):
            target = by_name.get((paper.get("title") or "").strip().lower())
            if target is not None:
                others = [other for other in target["papers"] if other is not paper]
                if len(others) >= 2:
                    removed += 1
                    continue
            kept.append(paper)
        session["papers"] = kept

    if removed:
        year_data["sessions"] = [s for s in sessions if s.get("papers")]
    return removed


WEB_PROGRAMMES_PATH = Path(__file__).resolve().parent / "data" / "programmes.tsv"
_web_programmes: Optional[Dict[Tuple[str, int], str]] = None


def web_programme_url(conference_id: str, year: int) -> Optional[str]:
    """
    A programme PDF published on the conference's own site, if one is listed.

    IEEE indexes no front-matter programme for a number of years; the
    conference usually still publishes one. See data/programmes.tsv.
    """

    global _web_programmes
    if _web_programmes is None:
        table: Dict[Tuple[str, int], str] = {}
        if WEB_PROGRAMMES_PATH.exists():
            for raw in WEB_PROGRAMMES_PATH.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                parts = [p.strip() for p in line.split("\t") if p.strip()]
                if len(parts) < 3:
                    continue
                try:
                    table[(parts[0], int(parts[1]))] = parts[2]
                except ValueError:
                    continue
        _web_programmes = table
    return _web_programmes.get((conference_id, year))


HTML_TAG_RE = re.compile(r"<[^>]+>")
HTML_BLOCK_RE = re.compile(r"</(?:p|div|tr|li|h[1-6]|table|br)\s*>|<br\s*/?>", re.IGNORECASE)


def _html_to_text(markup: str) -> str:
    """Flatten a programme page to the line-per-entry shape the parser wants."""

    text = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", markup)
    text = HTML_BLOCK_RE.sub("\n", text)
    text = HTML_TAG_RE.sub(" ", text)
    # Decode every entity, not a hand-picked few: CICC's pages write their
    # en dashes as "&#8211;", and a paper line reading "14-1 &#8211; Title"
    # matches no rule at all, which silently lost two days of one year.
    text = html.unescape(text).replace(" ", " ")
    lines = [re.sub(r"[ \t]{2,}", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def download_web_programme(url: str, cache_path: Path) -> Optional[bytes]:
    """Fetch a conference-hosted programme, caching it like any other."""

    if cache_path.exists():
        data = cache_path.read_bytes()
        if data[:5] == b"%PDF-":
            return data
    # A plain GET: retrying_get parses JSON, and this is a PDF. No IEEE rate
    # limiter either - this is the conference's own site, not Xplore.
    try:
        response = get_session().get(url, timeout=90)
        data = response.content
    except Exception as exc:                      # noqa: BLE001 - any failure is skippable
        logger.warning("Could not fetch the conference programme %s: %s", url, exc)
        return None
    if response.status_code != 200:
        logger.warning("%s returned HTTP %s", url, response.status_code)
        return None
    if not data:
        logger.warning("%s returned nothing", url)
        return None
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    if data[:5] == b"%PDF-":
        cache_path.write_bytes(data)
    return data


def web_programme_text(urls: str, cache_dir: Path, year: int) -> Optional[str]:
    """
    Text of a conference-hosted programme, whatever form it is published in.

    `urls` may list several comma-separated pages - CICC 2000 splits its
    programme across tp0.html .. tp7.html - and they are concatenated in order.
    """

    parts: List[str] = []
    for index, url in enumerate((u.strip() for u in urls.split(",")), start=1):
        if not url:
            continue
        suffix = "" if index == 1 else f"-{index}"
        pdf_path = cache_dir / f"{year}-web{suffix}.pdf"
        data = download_web_programme(url, pdf_path)
        if data is None:
            continue
        if data[:5] == b"%PDF-":
            parts.append(extract_text(data))
            continue
        # Not a PDF: treat it as a programme page.
        try:
            markup = data.decode("utf-8", errors="replace")
        except Exception:                                    # noqa: BLE001
            continue
        text = _html_to_text(markup)
        if text:
            (cache_dir / f"{year}-web{suffix}.txt").write_text(text, encoding="utf-8")
            parts.append(text)
    return "\n".join(parts) if parts else None

__all__ = [
    "drop_session_overview_records",
    "web_programme_url",
    "download_web_programme",
    "web_programme_text",
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
