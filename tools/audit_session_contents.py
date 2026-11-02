"""
Check that a session's papers actually belong under its name.

The HTML review covers how a page renders; the front-matter audit covers what
is a paper. Neither notices a session whose *contents are wrong* - ESSCIRC
2023 showed three mm-wave radar papers filed under "Plenary Keynote 1: Jose
Epifanio da Franca", and every mechanical check passed it.

Five signals, each cheap and each grounded in how a real programme is shaped:

  * a keynote or plenary holds one talk, not a run of technical papers;
  * a session named after a person is a keynote, so the same rule applies;
  * a session count approaching the paper count means something that is not
    a heading is being read as one;
  * a gap in the printed session codes means a session was never parsed, and
    its papers had to land somewhere - usually the session before it. This is
    the check that would have caught ESSCIRC 2023;
A shared-vocabulary check was tried and removed: singular/plural alone made it
fire on correct sessions ("IoT and Wireless Receivers" holding receiver papers),
and a check that cries wolf is worse than no check.

Everything here reports candidates for a human or an agent to read. None of it
edits data.

    python tools/audit_session_contents.py [source ...]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import CONFERENCES, get_config  # noqa: E402

CONFERENCE_SOURCES = ("isscc", "rfic", "cicc", "esscirc", "vlsi", "asscc")  # [c]

KEYNOTE_RE = re.compile(r"\b(keynote|plenary)\b", re.IGNORECASE)
# "Keynote 2: Brendan Farley" - used only to describe a keynote, never on its
# own: too many real session names end in a capitalised topical phrase.
PERSON_TAIL_RE = re.compile(r":\s*[A-Z][a-zA-Z.\-']+(?:\s+[A-Z][a-zA-Z.\-']+){1,3}\s*$")
# A paper reports a measurement; a keynote title does not.
METRIC_RE = re.compile(
    r"\d\s*(?:nm|um|µm|mm|GHz|MHz|kHz|Gb/s|Mb/s|GS/s|MS/s|dB|dBm|dBc|mW|µW|uW|nW|pJ|fJ|"
    r"TOPS|GOPS|V|mV|mA|µA|ppm|ENOB|SNDR|bit|b)\b",
    re.IGNORECASE,
)
STOP_WORDS = {
    "and", "for", "the", "with", "in", "of", "a", "an", "to", "on", "using",
    "techniques", "technique", "circuits", "circuit", "systems", "system",
    "design", "designs", "advanced", "novel", "session", "sessions", "part",
}


def words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{4,}", (text or "").lower()) if w not in STOP_WORDS}


def audit(source: str) -> int:
    config = get_config(source, create_dirs=False)
    if not config.json_dir.exists():
        return 0

    findings = 0
    for path in sorted(config.json_dir.glob("*.json")):
        if not re.fullmatch(r"\d{4}", path.stem):
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            continue
        sessions = data.get("sessions", [])
        year = path.stem

        for session in sessions:
            name = session.get("session_name", "")
            papers = session.get("papers", [])
            if not papers:
                continue

            # 1 & 2: a keynote, or a session named after a person, holding a
            # run of papers that report measurements.
            # Require the word itself: a trailing capitalised phrase alone is
            # not evidence, or "Technology Directions: Advanced Memory" reads
            # as a person's name.
            is_keynote = bool(KEYNOTE_RE.search(name))
            if is_keynote and len(papers) > 1:
                measured = [p for p in papers if METRIC_RE.search(p.get("title") or "")]
                if measured:
                    findings += 1
                    print(f"  {source} {year} [{session.get('session_code')}] {name!r}")
                    print(f"      holds {len(papers)} papers, {len(measured)} reporting measurements:")
                    for paper in measured[:4]:
                        print(f"        {paper.get('article_number')} | {(paper.get('title') or '')[:72]}")

        # The mirror of over-detection: a year with only a handful of sessions
        # holding a hundred papers each. The collapsed-year check elsewhere
        # tests for a single session, so one real session plus an Unassigned
        # bucket reads as two and slips past it - which is how CICC 2015 and
        # 2018 sat at 2 sessions for 123 and 109 papers unnoticed.
        real = [
            s for s in sessions
            if s.get("session_name") not in ("Unassigned", "General")
        ]
        papers_total = sum(len(s.get("papers", [])) for s in sessions)
        if papers_total > 20 and len(real) <= 4:
            biggest = max((len(s.get("papers", [])) for s in real), default=0)
            findings += 1
            print(f"  {source} {year}: only {len(real)} real session(s) for "
                  f"{papers_total} papers (largest holds {biggest}) - under-detected")

        # A real session groups several papers. When a year's session count
        # approaches its paper count, something that is not a heading is being
        # read as one - VLSI 2025 had 111 "sessions" for 140 papers because a
        # paper code ("C8-3") matched the session-header pattern.
        paper_count = sum(len(s.get("papers", [])) for s in sessions)
        singles = sum(1 for s in sessions if len(s.get("papers", [])) == 1)
        if paper_count > 20 and len(sessions) > paper_count * 0.45:
            findings += 1
            print(f"  {source} {year}: {len(sessions)} sessions for {paper_count} papers "
                  f"({singles} hold a single paper) - headings are being over-detected")

        # 3: gaps in the printed numeric session codes.
        numeric = sorted(
            int(s["session_code"]) for s in sessions
            if str(s.get("session_code") or "").isdigit()
        )
        if len(numeric) >= 5:
            missing = [n for n in range(numeric[0], numeric[-1] + 1) if n not in numeric]
            if missing:
                findings += 1
                print(f"  {source} {year}: session codes {missing} never parsed "
                      f"(range {numeric[0]}-{numeric[-1]}); their papers landed elsewhere")
    return findings


def main() -> int:
    wanted = [a for a in sys.argv[1:] if a in CONFERENCES] or list(CONFERENCE_SOURCES)
    total = 0
    for source in wanted:
        print("=" * 72)
        print(source)
        print("=" * 72)
        found = audit(source)
        total += found
        if not found:
            print("  nothing to look at")
    print()
    print(f"{total} finding(s). These are candidates to read, not verdicts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
