# [c] whole file
"""
Re-clean stored abstracts that still show JATS/MathML markup. (Claude, 2026-11-02)

The full-abstract endpoint writes tags with attributes (<sup xmlns:mml=...>,
<inline-formula><tex-math>...</tex-math></inline-formula>, <para>, <xref>),
which textclean missed until 2026-11-02: 17,974 abstracts showed raw tags,
and the closing </sup>/</sub> had already been stripped from them.
textclean._strip_markup now handles both the raw and the damaged form, so this
re-runs clean_text over every affected abstract in:

* cache/<id>/abstracts_full.json (the source the scraper re-applies), and
* output/<id>/json/<year>.json and early_access.json, in place.

    python tools/repair_abstract_markup.py --dry-run
    python tools/repair_abstract_markup.py

Refuses to run while restore_abstracts.py holds its lock: that process keeps the
old text in memory and would write it back.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import CONFERENCES, get_config  # noqa: E402
from textclean import _MARKUP_TAGS, clean_text  # noqa: E402
from utils import load_json, save_json  # noqa: E402

LOCK = Path(__file__).resolve().parent.parent / "cache" / "abstract_restore.lock"
HAS_MARKUP = re.compile(rf"<\s*/?\s*({_MARKUP_TAGS})\b", re.IGNORECASE)


def _papers(data):
    if "papers" in data:
        return data["papers"]
    return [p for s in data.get("sessions", []) for p in s.get("papers", [])]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if LOCK.exists() and not args.dry_run:
        print(f"{LOCK.name} exists: wait for restore_abstracts.py to finish (or remove a stale lock).")
        return 1

    cache_fixed = year_fixed = files_written = left = 0
    for cid in CONFERENCES:
        config = get_config(cid)
        cache_path = config.cache_dir / "abstracts_full.json"
        if cache_path.exists():
            cache = load_json(cache_path)
            changed = 0
            for article, text in cache.items():
                if HAS_MARKUP.search(text):
                    cache[article] = clean_text(text)
                    changed += 1
            cache_fixed += changed
            if changed and not args.dry_run:
                save_json(cache_path, cache)
                files_written += 1
        for path in sorted(config.json_dir.glob("*.json")):
            if not (path.stem.isdigit() or path.stem == "early_access"):
                continue
            data = load_json(path)
            changed = 0
            for paper in _papers(data):
                text = paper.get("abstract") or ""
                if HAS_MARKUP.search(text):
                    paper["abstract"] = clean_text(text)
                    changed += 1
                    left += bool(HAS_MARKUP.search(paper["abstract"]))
            year_fixed += changed
            if changed and not args.dry_run:
                save_json(path, data)
                files_written += 1
    print(f"{'Would fix' if args.dry_run else 'Fixed'}: {cache_fixed} cached abstracts, "
          f"{year_fixed} abstracts in year files; {files_written} files written; "
          f"{left} still with markup after cleaning.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
