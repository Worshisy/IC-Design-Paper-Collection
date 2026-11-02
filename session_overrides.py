"""
Hand-curated session assignments for papers no parser rule can place.

A past conference year never changes, so once a paper's real session has been
read off the printed programme it is a fact, not a guess. Some years defeat
every parser rule - a two-column scan whose OCR separates a paper code from
its title, a programme IEEE never published - and chasing those with ever more
regexes costs more than it returns and risks breaking years that already work.

Entries live in `data/session_overrides.tsv`, one per line:

    conference <TAB> year <TAB> article_number <TAB> session_code <TAB> session_name

The override is applied last, after parsing and after any track filter, so it
survives a re-parse and an incremental update. A paper named here is moved out
of whatever bucket it landed in and into the named session, which is created if
the year does not already have it. Papers are matched on article number, which
is stable in Xplore.

This is deliberately a data file rather than code: adding a line needs no
review of parsing logic, and `tools/audit_session_overrides.py` reports any
entry that no longer matches anything, so a stale line cannot rot silently.
"""

from __future__ import annotations

import logging
import statistics  # [c]
from pathlib import Path
from typing import Dict, List, Optional, Tuple  # [c]

logger = logging.getLogger(__name__)

DATA_PATH = Path(__file__).resolve().parent / "data" / "session_overrides.tsv"

# A session_name of this value means "this record is not a paper, remove it".
DROP_MARKER = "__DROP__"

# (conference, year) -> {article_number: (session_code, session_name)}
_cache: Dict[Tuple[str, int], Dict[str, Tuple[str, str]]] | None = None


def load_overrides() -> Dict[Tuple[str, int], Dict[str, Tuple[str, str]]]:
    """Read the override table, once per process."""

    global _cache
    if _cache is not None:
        return _cache

    table: Dict[Tuple[str, int], Dict[str, Tuple[str, str]]] = {}
    if DATA_PATH.exists():
        for number, raw in enumerate(DATA_PATH.read_text(encoding="utf-8").splitlines(), 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = [part.strip() for part in line.split("\t")]
            if len(parts) < 5:
                logger.warning("%s:%d: expected 5 tab-separated fields", DATA_PATH.name, number)
                continue
            conference, year_text, article, code, name = parts[:5]
            try:
                year = int(year_text)
            except ValueError:
                logger.warning("%s:%d: %r is not a year", DATA_PATH.name, number, year_text)
                continue
            table.setdefault((conference, year), {})[article] = (code, name)
    _cache = table
    return table


def _page(paper: dict) -> Optional[int]:  # [c]
    try:
        return int(paper.get("start_page"))
    except (TypeError, ValueError):
        return None


def _print_order(sessions: List[dict], wanted: Dict[str, Tuple[str, str]]) -> List[dict]:  # [c]
    """
    Put what an override placed where the proceedings print it.

    A moved paper used to land at the end of its session, and a session an
    override created at the front of the year: A-SSCC 2012 read
    "I2 1 3 P2 5 7 ... P1 I1 2 4 6". Only overridden papers, and sessions made
    entirely of them, move; everything else keeps the order it had.
    """

    def named(paper: dict) -> bool:
        return str(paper.get("article_number") or "") in wanted

    real = [s for s in sessions if s.get("session_name") != "Unassigned"]
    rest = [s for s in sessions if s.get("session_name") == "Unassigned"]

    # Papers: page order, but only where the session's pages are all present
    # and all different. A-SSCC 2010 stores "1" for every paper and ISSCC 2002
    # interleaves two volumes; both stay as they were.
    for session in real:
        papers = session.get("papers", [])
        pages = [_page(paper) for paper in papers]
        if (
            any(named(paper) for paper in papers)
            and None not in pages
            and len(set(pages)) == len(pages)
        ):
            session["papers"] = sorted(papers, key=_page)

    made = [s for s in real if s.get("papers") and all(named(p) for p in s["papers"])]
    if not made:
        return real + rest
    base = [s for s in real if not any(s is m for m in made)]

    codes = [str(s.get("session_code") or "") for s in real]
    if all(code.isdigit() for code in codes):
        # "Session N" is its own order, whatever the pages say: A-SSCC 2018
        # paginates its plenaries separately, so their pages collide.
        position = {id(s): int(s["session_code"]) for s in real}
        movable = made
    else:
        every = [_page(p) for s in real for p in s.get("papers", [])]
        good = [value for value in every if value is not None]
        if not good or len(good) < 0.9 * len(every) or len(set(good)) < 0.9 * len(good):
            return real + rest
        spans: Dict[int, List[int]] = {
            id(s): sorted(v for v in (_page(p) for p in s["papers"]) if v is not None)
            for s in real
        }
        position = {
            key: (statistics.median(pages) if pages else None) for key, pages in spans.items()
        }

        def contiguous(session: dict) -> bool:
            # Invited papers scattered through a volume have no place in page
            # order; leave such a session where it was.
            pages = spans[id(session)]
            return bool(pages) and not any(
                position[id(other)] is not None and pages[0] < position[id(other)] < pages[-1]
                for other in real
                if other is not session
            )

        movable = [s for s in made if contiguous(s)]

    anchors = [position[id(s)] for s in base]
    if None in anchors or anchors != sorted(anchors):
        return real + rest

    ordered = [s for s in real if not any(s is m for m in movable)]
    for session in sorted(movable, key=lambda s: position[id(s)]):
        for index, other in enumerate(ordered):
            if any(other is b for b in base) and position[id(other)] > position[id(session)]:
                ordered.insert(index, session)
                break
        else:
            ordered.append(session)
    return ordered + rest


def apply_overrides(conference_id: str, year: int, year_data: dict) -> int:
    """
    Move listed papers into their real sessions. Returns papers moved.

    A year with no entries is left untouched, which is nearly all of them.
    """

    wanted = load_overrides().get((conference_id, year))
    if not wanted:
        return 0

    sessions: List[dict] = year_data.get("sessions", [])
    if not sessions:
        return 0

    # Pull out every paper the table names, wherever it currently sits.
    # A session_name of DROP_MARKER removes the record instead of moving it:
    # a one-off for a non-paper too specific to be worth a parser rule.
    taken: Dict[str, dict] = {}
    dropped = 0
    for session in sessions:
        kept = []
        for paper in session.get("papers", []):
            article = str(paper.get("article_number") or "")
            if article in wanted:
                if wanted[article][1] == DROP_MARKER:
                    dropped += 1
                else:
                    taken[article] = paper
            else:
                kept.append(paper)
        session["papers"] = kept

    if not taken and not dropped:
        return 0

    # Index by (code, name) first: a year can reuse a session name - VLSI 2012
    # names its sessions after the room, and "Coral Ballroom 4" appears more
    # than once - and a name-only index would merge two distinct sessions.
    by_key = {}
    for session in sessions:
        by_key.setdefault(
            (session.get("session_code") or "", session.get("session_name")), session
        )
        by_key.setdefault((None, session.get("session_name")), session)

    for article, paper in taken.items():
        code, name = wanted[article]
        target = by_key.get((code, name)) or by_key.get((None, name))
        if target is None:
            target = {
                "session_number": 0,       # renumbered below
                "session_code": code,
                "session_name": name,
                "papers": [],
            }
            sessions.append(target)
            by_key[(code, name)] = target
            by_key.setdefault((None, name), target)
        elif code and not target.get("session_code"):
            target["session_code"] = code
        target["papers"].append(paper)

    # Drop anything left empty, then renumber so the page reads in order.
    sessions = [session for session in sessions if session.get("papers")]
    sessions.sort(key=lambda s: (s.get("session_name") == "Unassigned", s.get("session_number") or 0))
    sessions = _print_order(sessions, wanted)  # [c]
    for position, session in enumerate(sessions, start=1):
        session["session_number"] = position
        prefix = session.get("session_code") or str(position)
        for index, paper in enumerate(session["papers"], start=1):
            number = f"{prefix}.{index}"
            paper["session_number"] = position
            paper["session_name"] = session["session_name"]
            paper["paper_number"] = number
            paper["inferred_paper_number"] = number

    year_data["sessions"] = sessions
    logger.info(
        "[%s %s] override: %d paper(s) placed, %d removed",
        conference_id, year, len(taken), dropped,
    )
    return len(taken) + dropped


__all__ = ["apply_overrides", "load_overrides", "DATA_PATH", "DROP_MARKER"]
