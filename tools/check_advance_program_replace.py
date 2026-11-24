"""Regression check: a real scrape replaces Advance Program placeholders. No network use.

Runs the scraper's merge steps (``_restore_session_layout`` and
``_drop_advance_program_papers``) on a COPY of ``output/isscc/json/2027.json``
(built by ``tools/import_advance_program.py``) in a temp dir.

    D:\\anaconda3\\python.exe tools/check_advance_program_replace.py
"""  # [c]

from __future__ import annotations

import copy
import shutil
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import get_config  # noqa: E402
from scraper import ADVANCE_PROGRAM_SOURCE, Scraper  # noqa: E402
from utils import load_json  # noqa: E402


def fresh_year(papers):
    sessions = [{"session_number": 1, "session_code": "1", "session_name": "Fresh", "papers": papers}] if papers else []
    return {"year": 2027, "proceedings_url": "x", "sessions": sessions}


def main() -> int:
    source = ROOT / "output" / "isscc" / "json" / "2027.json"
    placeholders = [p for s in load_json(source)["sessions"] for p in s["papers"]]
    assert placeholders and all(p["source"] == ADVANCE_PROGRAM_SOURCE for p in placeholders)
    failures = []

    with tempfile.TemporaryDirectory() as tmp:
        cfg = replace(get_config("isscc", create_dirs=False), json_dir=Path(tmp))
        shutil.copy(source, Path(tmp) / "2027.json")
        scraper = Scraper(config=cfg, overwrite=False)

        def check(label, ok, detail=""):
            print(("PASS " if ok else "FAIL ") + label + (f"  {detail}" if detail else ""))
            if not ok:
                failures.append(label)

        check("AP-only year file is recognised", scraper._is_advance_program_year(Path(tmp) / "2027.json"))

        # 1. empty fresh list
        data = fresh_year([])
        restored = scraper._restore_session_layout(2027, data, keep_articles=set())
        dropped = scraper._drop_advance_program_papers(2027, data)
        check("empty fresh list: layout restore does nothing", restored is False)
        check("empty fresh list: no placeholder left, count logged", not data["sessions"] and dropped == len(placeholders),
              f"dropped={dropped} of {len(placeholders)}")

        # 2. one fake fresh paper
        fake = {"title": "Fake", "article_number": "99999999", "paper_number": "1.1", "authors": ["A B"], "affiliations": ["X"]}
        data = fresh_year([copy.deepcopy(fake)])
        restored = scraper._restore_session_layout(2027, data, keep_articles={"99999999"})
        scraper._drop_advance_program_papers(2027, data)
        papers = [p for s in data["sessions"] for p in s["papers"]]
        check("fake fresh paper: only it remains", [p["article_number"] for p in papers] == ["99999999"],
              f"restored={restored}, papers={len(papers)}")
        check("fake fresh paper: no advance_program source", all(p.get("source") != ADVANCE_PROGRAM_SOURCE for p in papers))

        # 3. a placeholder leaking into the fresh data is stripped
        data = fresh_year([copy.deepcopy(fake), copy.deepcopy(placeholders[0])])
        removed = scraper._drop_advance_program_papers(2027, data)
        left = [p for s in data["sessions"] for p in s["papers"]]
        check("leaked placeholder in fresh data is removed", len(left) == 1 and left[0]["article_number"] == "99999999",
              f"removed={removed}")

        # 4. a year file with a real paper is not an AP year
        mixed = load_json(Path(tmp) / "2027.json")
        mixed["sessions"][0]["papers"][0] = copy.deepcopy(fake)
        (Path(tmp) / "2028.json").write_text(__import__("json").dumps(mixed), encoding="utf-8")
        check("year file with a real paper is not an AP year", not scraper._is_advance_program_year(Path(tmp) / "2028.json"))

    print("ALL PASS" if not failures else f"FAILED: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
