"""
Check `data/session_overrides.tsv` against the data it claims to fix.

An override is a hand-written fact about a fixed past year, so it has exactly
the failure mode every hand-written list has: it can stop matching - a paper
re-numbered, a year re-pulled, a session renamed - and then it quietly does
nothing. This reports each entry as applied, already-applied, or stale.

Run after editing the table:
    python tools/audit_session_overrides.py
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import session_overrides  # noqa: E402
from config import get_config  # noqa: E402


def main() -> int:
    table = session_overrides.load_overrides()
    if not table:
        print(f"{session_overrides.DATA_PATH} holds no entries.")
        return 0

    stale: list[str] = []
    applied = dropped = pending = 0
    per_source: dict[str, int] = defaultdict(int)

    for (conference, year), wanted in sorted(table.items()):
        path = get_config(conference, create_dirs=False).json_dir / f"{year}.json"
        if not path.exists():
            stale.append(f"{conference} {year}: no data file")
            continue

        data = json.loads(path.read_text(encoding="utf-8"))
        placement: dict[str, str] = {}
        for session in data.get("sessions", []):
            for paper in session.get("papers", []):
                placement[str(paper.get("article_number") or "")] = session.get("session_name", "")

        for article, (_, name) in sorted(wanted.items()):
            per_source[conference] += 1
            where = placement.get(article)
            if name == session_overrides.DROP_MARKER:
                if where is None:
                    dropped += 1          # gone, as intended
                else:
                    pending += 1
                    stale.append(
                        f"{conference} {year} {article}: marked __DROP__ but still present in {where!r}"
                    )
            elif where is None:
                stale.append(
                    f"{conference} {year} {article}: names a paper this year does not contain"
                )
            elif where == name:
                applied += 1
            else:
                pending += 1
                stale.append(
                    f"{conference} {year} {article}: wants {name!r}, currently in {where!r}"
                )

    total = sum(per_source.values())
    print(f"{total} override entries across {len(per_source)} source(s):")
    for conference, count in sorted(per_source.items()):
        print(f"  {conference:9s} {count}")
    print()
    print(f"  {applied} in place, {dropped} removed as intended, {pending} not yet applied")

    if stale:
        print()
        print(f"{len(stale)} entry/entries need attention:")
        for line in stale:
            print(f"  {line}")
        print()
        print("'not yet applied' usually just means the year has not been rebuilt since")
        print("the entry was added. An entry naming a paper the year does not contain is")
        print("genuinely stale and should be removed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
