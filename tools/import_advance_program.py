"""Import a conference Advance Program (text from ``pdftotext -layout``) into a year file.

Built for ISSCC 2027 (draft 2026-11-23). Only numbered papers ``N.M`` become
records; tutorials, forums, short courses and events are skipped. Every record
carries ``source = "advance_program"`` so a real scrape can find and drop them
(``scraper.ADVANCE_PROGRAM_SOURCE``). No network use.

    D:\\anaconda3\\python.exe tools/import_advance_program.py            # write + check
    D:\\anaconda3\\python.exe tools/import_advance_program.py --dry-run  # check only
"""  # [c]

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent

PROGRAM_URL = "https://submissions.mirasmart.com/ISSCC2027/PDF/ISSCC2027AdvanceProgram.pdf"
PROGRAM_DATE = "2026-11-23"
YEAR = 2027
CONFERENCE_NAME = "2027 IEEE International Solid-State Circuits Conference (ISSCC)"
CONFERENCE_DATES = "14-18 Feb. 2027"  # cover: "FEBRUARY 14, 15, 16, 17, 18"
CONFERENCE_LOCATION = "San Francisco, Marriott Marquis Hotel"
SOURCE = "advance_program"

LIGATURES = {"\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl", "\ufb03": "ffi", "\ufb04": "ffl",
             "\u00a0": " ", "\u2009": " ", "\u200b": ""}

RE_SESSION = re.compile(r"^\s*SESSION\s+(\d+)\b(.*)$")
RE_PAPER = re.compile(r"^(\s{0,12})(\d{1,2})\.(\d{1,2})\s+(\S.*)$")
RE_TIME = re.compile(r"^\s*\d{1,2}:\d{2}\s*[AP]M\s*$")
RE_BREAK = re.compile(r"^\s*(Break|Conclusion|BREAK|CONCLUSION)\b.*\d{1,2}:\d{2}\s*[AP]M\s*$")
RE_DAYHEAD = re.compile(r"^\s*(Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day,?\s+February\s+\d+\w*,?\s+\d{1,2}:\d{2}\s*[AP]M\s*$")
RE_PAGENO = re.compile(r"^\s{20,}\d{1,3}\s*$")
RE_AFFNO = re.compile(r"^\s{0,12}(\d{1,2})\s*$")
RE_CHAIR = re.compile(r"^\s*(Session\s+)?(Co-)?(Associate\s+)?Chairs?\b|^\s*Session\s+Co-?Chairs?\b", re.I)
RE_REGION_END = re.compile(r"^\s*(FORUM|SHORT COURSE|TUTORIAL)\s*\d*\s*$")

# One author as printed: initials, then a surname, then superscripts and/or "*".
_UP = "A-ZÀ-ÖØ-Þ"  # accented capitals too (Ö. Urhan)
_INIT = rf"[{_UP}][A-Za-z]?(?:-[{_UP}][A-Za-z]?)?\."
RE_AUTHOR = re.compile(rf"^(?:{_INIT}\s?)+[^\s,\d*]+(?:[ -][^\s,\d*]+)*[*\u2020\u2021]*[\d,*\u2020\u2021]*$")
RE_SUPER = re.compile(r"^(?P<name>.*?)(?P<sup>[*\u2020\u2021]*\d*(?:,\d+)*[*\u2020\u2021]*)$")


def clean(text: str) -> str:
    for src, dst in LIGATURES.items():
        text = text.replace(src, dst)
    return re.sub(r"\s+", " ", text).strip()


def indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


RE_INITIALS_ONLY = re.compile(rf"^(?:{_INIT}\s?)+$")  # a name cut after its initials by a line wrap
RE_SURNAME_ONLY = re.compile(r"^[^\s,\d*]+(?:[ -][^\s,\d*]+)*[*†‡]*[\d,*†‡]*$")
RE_ECA = re.compile(r",?\s*\*\s*Equally Credited Authors \(ECAs\)")
RE_AUTHORS_TBD = re.compile(r"Author list to come", re.I)


def is_author_line(line: str, after_initials: bool = False) -> bool:
    """A comma-separated run of authors; the last may be cut after its initials, and the
    first may be the surname that completes the previous line's cut name."""
    text = clean(line).rstrip(",").strip()
    if not text:
        return False
    parts = [p.strip() for p in re.split(r",\s+", text) if p.strip()]
    for position, part in enumerate(parts):
        if RE_AUTHOR.match(part):
            continue
        if position == len(parts) - 1 and RE_INITIALS_ONLY.match(part):
            continue
        if position == 0 and after_initials and RE_SURNAME_ONLY.match(part):
            continue
        return False
    return True


def ends_open(line: str) -> bool:
    """Does the author list go on in the next line?"""
    text = clean(line)
    if text.endswith(","):
        return True
    last = re.split(r",\s+", text)[-1].strip()
    return bool(RE_INITIALS_ONLY.match(last))


def parse_numbered(text: str) -> Dict[int, str]:
    """'1 A, X; 2B, Y 3 C' -> {1: 'A, X', 2: 'B, Y', 3: 'C'}: markers 1, 2, 3... in order."""
    starts: List[Tuple[int, int, int]] = []  # number, marker start, text start
    position = 0
    number = 1
    while True:
        match = re.compile(rf"(?:^|(?<=[\s;])){number}\s*(?=[^\W\d_])").search(text, position)
        if not match:
            break
        starts.append((number, match.start(), match.end()))
        position = match.end()
        number += 1
    table: Dict[int, str] = {}
    for index, (num, _, begin) in enumerate(starts):
        end = starts[index + 1][1] if index + 1 < len(starts) else len(text)
        table[num] = text[begin:end].strip(" ;,")
    return table


def split_authors(joined: str) -> List[Tuple[str, List[int]]]:
    """'P. Park1,2, W. Kim*1' -> [('P. Park', [1, 2]), ('W. Kim', [1])]"""
    out: List[Tuple[str, List[int]]] = []
    for token in re.split(r",\s+", clean(joined).rstrip(",")):
        token = token.strip()
        if not token:
            continue
        match = RE_SUPER.match(token)
        name = match.group("name").strip()
        sup = match.group("sup")
        numbers = [int(n) for n in re.findall(r"\d+", sup)]
        out.append((name, numbers))
    return out


def read_lines(text_path: Path) -> List[Tuple[int, str]]:
    """Lines with the 1-based PDF page each sits on (pdftotext puts \\f between pages)."""
    lines: List[Tuple[int, str]] = []
    page = 1
    for raw in text_path.read_text(encoding="utf-8").split("\n"):
        while "\f" in raw:
            head, raw = raw.split("\f", 1)
            if head.strip():
                lines.append((page, head))
            page += 1
        lines.append((page, raw.rstrip()))
    return lines


def region(lines: List[Tuple[int, str]]) -> List[Tuple[int, str]]:
    start = next(i for i, (_, l) in enumerate(lines) if re.match(r"^SESSION 1\s+Monday", l))
    end = len(lines)
    seen_last = False
    for i in range(start, len(lines)):
        m = RE_SESSION.match(lines[i][1])
        if m and int(m.group(1)) == 40:
            seen_last = True
        if seen_last and RE_REGION_END.match(lines[i][1]):
            end = i
            break
    return lines[start:end]


def collect_blocks(rows: List[Tuple[int, str]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Walk the program once; return raw paper blocks and per-session names."""
    blocks: List[Dict[str, Any]] = []
    sessions: Dict[int, str] = {}
    session = 0
    title_lines: List[str] = []
    collecting_title = False
    current: Optional[Dict[str, Any]] = None

    for page, line in rows:
        head = RE_SESSION.match(line)
        if head and (not head.group(2).strip() or re.match(r"\s*(Mon|Tues|Wednes)day", head.group(2))):
            number = int(head.group(1))
            current = None
            if number != session:
                session = number
                title_lines = []
                collecting_title = True
            continue
        if collecting_title:
            if RE_CHAIR.match(line) or RE_TIME.match(line) or RE_PAPER.match(line):
                sessions[session] = clean(" ".join(title_lines))
                collecting_title = False
            else:
                if line.strip() and not RE_PAGENO.match(line) and not RE_DAYHEAD.match(line):
                    title_lines.append(line)
                continue
        paper = RE_PAPER.match(line)
        if paper and int(paper.group(2)) == session:
            number = f"{paper.group(2)}.{paper.group(3)}"
            text_col = paper.start(4)
            current = {"session": session, "number": number, "page": page, "title_col": text_col,
                       "lines": [paper.group(4)]}
            blocks.append(current)
            continue
        if current is None:
            continue
        if RE_TIME.match(line) or RE_BREAK.match(line):
            current = None
            continue
        if not line.strip() or RE_PAGENO.match(line) or RE_DAYHEAD.match(line):
            continue
        current["lines"].append(line)
    return blocks, sessions


def parse_plenary(block: Dict[str, Any]) -> Dict[str, Any]:
    """1.k: title, then 'Name, Role,' and 'Company, City' lines, then the abstract (dropped)."""
    title_col = block["title_col"]
    lines = block["lines"]
    title = [lines[0]]
    index = 1
    while index < len(lines) and indent_of(lines[index]) <= title_col:
        title.append(lines[index])
        index += 1
    person: List[str] = []
    while index < len(lines) and indent_of(lines[index]) > title_col:  # the abstract is flush left
        person.append(lines[index])
        index += 1
    person_text = ""
    for part in (clean(l) for l in person):  # lines of "Name, Role" and "Company, City" join with a comma
        person_text += (" " if person_text.endswith(",") else ", " if person_text else "") + part
    name, _, role = person_text.partition(",")
    return {"title": clean(" ".join(title)), "authors": [clean(name)],
            "affiliations": [clean(role)], "raw": clean(role)}


def parse_regular(block: Dict[str, Any]) -> Dict[str, Any]:
    lines = block["lines"]
    index = 1
    title = [lines[0]]
    while index < len(lines) and not is_author_line(lines[index]) and not RE_AUTHORS_TBD.search(lines[index]):
        title.append(lines[index])
        index += 1
    author_lines: List[str] = []
    if index < len(lines) and RE_AUTHORS_TBD.search(lines[index]):
        index += 1  # "Author list to come."
    else:
        while index < len(lines) and is_author_line(lines[index], after_initials=bool(author_lines) and ends_open(author_lines[-1]) and not author_lines[-1].rstrip().endswith(",")):
            author_lines.append(lines[index])
            index += 1
            if not ends_open(author_lines[-1]):
                break
    rest_text = RE_ECA.sub("", clean(" ".join(lines[index:]))).strip(" ,")
    rest_text = re.sub(r"(^|\s)\*(?=now at)", r" ", rest_text)  # "*now at X" footnote affiliation
    authors = split_authors(" ".join(author_lines))
    problems: List[str] = []
    names = [a[0] for a in authors]
    per_author: List[str] = []
    if re.match(r"^1\s*[^\W\d_]", rest_text):
        table = parse_numbered(rest_text)
        for name, numbers in authors:
            if not numbers:
                problems.append(f"author without superscript: {name}")
                per_author.append("")
                continue
            parts = []
            for number in numbers:
                if number not in table:
                    problems.append(f"unresolved superscript {number} on {name}")
                else:
                    parts.append(table[number])
            per_author.append("; ".join(parts))
        unused = set(table) - {n for _, nums in authors for n in nums}
        if unused:
            problems.append(f"affiliation numbers never used: {sorted(unused)}")
    else:
        single = rest_text
        for name, numbers in authors:
            if numbers:
                problems.append(f"superscript {numbers} on {name} but no numbered affiliations")
        per_author = [single] * len(authors)
    seen: List[str] = []
    for text in per_author:
        for part in text.split("; "):
            if part and part not in seen:
                seen.append(part)
    if not authors and rest_text:
        seen = [rest_text]
    return {"title": clean(" ".join(title)), "authors": names, "affiliations": per_author,
            "raw": "; ".join(seen), "problems": problems}


def build_record(block: Dict[str, Any], session_name: str) -> Dict[str, Any]:
    parsed = parse_plenary(block) if block["session"] == 1 else parse_regular(block)
    session_name = "Plenary" if block["session"] == 1 else session_name
    return {
        "year": YEAR,
        "session_number": block["session"],
        "session_name": session_name,
        "paper_number": block["number"],
        "inferred_paper_number": block["number"],
        "title": parsed["title"],
        "abstract": "",
        "authors": parsed["authors"],
        "affiliations": parsed["affiliations"],
        "author_affiliations_raw": parsed["raw"],
        "conference_name": CONFERENCE_NAME,
        "conference_dates": CONFERENCE_DATES,
        "conference_location": CONFERENCE_LOCATION,
        "displayed_paper_number": block["number"],
        "paper_url": "",
        "url": f"{PROGRAM_URL}#page={block['page']}",
        "source": SOURCE,
        "_problems": parsed.get("problems", []),
    }


def build_year(text_path: Path) -> Tuple[Dict[str, Any], List[str]]:
    rows = region(read_lines(text_path))
    blocks, names = collect_blocks(rows)
    sessions: Dict[int, List[Dict[str, Any]]] = {}
    for block in blocks:
        sessions.setdefault(block["session"], []).append(build_record(block, names.get(block["session"], "")))
    problems: List[str] = []
    year_sessions = []
    for number in sorted(sessions):
        papers = sessions[number]
        for paper in papers:
            for item in paper.pop("_problems"):
                problems.append(f"{paper['paper_number']}: {item}")
        year_sessions.append({"session_number": number, "session_code": str(number),
                              "session_name": papers[0]["session_name"], "papers": papers})
    year_data = {
        "year": YEAR,
        "proceedings_url": PROGRAM_URL,
        "source": SOURCE,
        "program_date": PROGRAM_DATE,
        "sessions": year_sessions,
        "conference_name": CONFERENCE_NAME,
        "conference_dates": CONFERENCE_DATES,
        "conference_location": CONFERENCE_LOCATION,
    }
    return year_data, problems


def run_checks(year_data: Dict[str, Any], problems: List[str]) -> bool:
    ok = True
    total = 0
    print("session | papers | numbering | name")
    for session in year_data["sessions"]:
        papers = session["papers"]
        total += len(papers)
        numbers = [p["paper_number"] for p in papers]
        expect = [f"{session['session_number']}.{i}" for i in range(1, len(papers) + 1)]
        good = numbers == expect and len(set(numbers)) == len(numbers)
        ok &= good
        print(f"{session['session_number']:>7} | {len(papers):>6} | {'ok' if good else 'GAP/DUP ' + str(numbers)} | {session['session_name']}")
    print(f"total papers: {total}, sessions: {len(year_data['sessions'])}")
    pending = [p["paper_number"] for s in year_data["sessions"] for p in s["papers"]
               if not p["authors"] and p["author_affiliations_raw"]]  # "Author list to come" in the program
    bad = [p["paper_number"] for s in year_data["sessions"] for p in s["papers"]
           if p["paper_number"] not in pending and (
               not p["authors"] or not p["affiliations"] or any(not a for a in p["affiliations"])
               or len(p["authors"]) != len(p["affiliations"]) or not p["title"])]
    odd = [p["paper_number"] for s in year_data["sessions"] for p in s["papers"]
           if len(p["title"]) > 260 or re.search(r"\d:\d\d|PM|AM", p["title"] + p["author_affiliations_raw"])
           or any(len(a) < 4 or len(a) > 60 for a in p["authors"])]
    print("author list marked 'to come' in the program (no authors kept):", pending or "none")
    print("odd titles/authors/affiliations (length, clock times):", odd or "none")
    print("papers without title / authors / full affiliations:", bad or "none")
    print("parser problems (unresolved superscripts etc.):", problems or "none")
    leftovers = [p["paper_number"] for s in year_data["sessions"] for p in s["papers"]
                 if re.search(r"\d$", "".join(p["authors"])) or any(re.search(r"[*\u2020]", a) for a in p["authors"])]
    print("author names with leftover superscript marks:", leftovers or "none")
    return ok and not bad and not problems and not leftovers


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--text", default=str(ROOT / "cache" / "isscc_ap" / "ap.txt"))
    parser.add_argument("--out", default=str(ROOT / "output" / "isscc" / "json" / f"{YEAR}.json"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--show", type=int, default=5, help="random papers to print in full")
    args = parser.parse_args()

    year_data, problems = build_year(Path(args.text))
    ok = run_checks(year_data, problems)
    papers = [p for s in year_data["sessions"] for p in s["papers"]]
    for paper in random.Random(2027).sample(papers, min(args.show, len(papers))):
        print(json.dumps(paper, ensure_ascii=False, indent=1))
    if not ok:
        print("CHECKS FAILED: nothing written", file=sys.stderr)
        return 1
    if args.dry_run:
        return 0
    out = Path(args.out)
    out.write_text(json.dumps(year_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out} ({len(papers)} papers)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
