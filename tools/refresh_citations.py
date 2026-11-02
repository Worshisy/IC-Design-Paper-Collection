# [c] whole file
"""
Refresh every paper's IEEE Xplore citation count.

The search API already returns `citationCount` with each record, so this is one
request per 100 papers (~900 requests, ~25 min for the whole corpus), not one
per paper. Per source and year it:

1. re-fetches that year's records and copies the new counts into the raw record
   cache (only the count fields; adding or dropping papers is a scrape's job),
2. writes `citation_count` into the year file and `early_access.json` in place
   - no re-parse, so the curated session layer is untouched,
3. records the fetch date in `output/citations_updated.json`.

    python tools/refresh_citations.py                    # everything, from IEEE
    python tools/refresh_citations.py --sources isscc,jssc
    python tools/refresh_citations.py --older-than 1     # resume: skip years done today
    python tools/refresh_citations.py --offline          # counts from the record cache

A failed year keeps its previous counts and is listed at the end.
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import CONFERENCES, get_config  # noqa: E402
from parser import citation_count  # noqa: E402
from scraper import Scraper  # noqa: E402
from utils import load_json, save_json, setup_logging  # noqa: E402

logger = logging.getLogger("citations")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
META_PATH = PROJECT_ROOT / "output" / "citations_updated.json"
COUNT_FIELDS = ("citationCount", "patentCitationCount")


def _refetch(scraper: Scraper, year: int, records: List[Dict[str, Any]]) -> int:
    """Copy fresh counts into `records` in place. Returns records changed."""

    pubs: List[str] = []
    for record in records:
        pub = str(record.get("publicationNumber") or "")
        if pub and pub not in pubs:
            pubs.append(pub)
    fresh: Dict[str, Dict[str, Any]] = {}
    for pub in pubs:
        for record in scraper._fetch_all_records_for_year(year, pub):
            article = str(record.get("articleNumber") or "")
            if article:
                fresh[article] = record
    changed = 0
    for record in records:
        new = fresh.get(str(record.get("articleNumber") or ""))
        if new is None:
            continue
        for field in COUNT_FIELDS:
            if field in new and new[field] != record.get(field):
                record[field] = new[field]
                changed += 1
    return changed


def _apply(papers: List[Dict[str, Any]], counts: Dict[str, Optional[int]]) -> int:
    changed = 0
    for paper in papers:
        article = str(paper.get("article_number") or "")
        if article in counts and paper.get("citation_count") != counts[article]:
            paper["citation_count"] = counts[article]
            changed += 1
    return changed


def refresh_source(conference_id: str, offline: bool, older_than: float,
                   meta: Dict[str, Dict[str, str]], failed: List[str]) -> None:
    config = get_config(conference_id, create_dirs=False)
    scraper = Scraper(config=config)
    record_dir = config.cache_dir / "records"
    if not record_dir.is_dir():
        return
    done = meta.setdefault(conference_id, {})
    today = dt.date.today()
    all_counts: Dict[str, Optional[int]] = {}

    for path in sorted(record_dir.glob("*.json")):
        if not path.stem.isdigit():
            continue
        year = int(path.stem)
        records = load_json(path) or []
        last = done.get(str(year))
        skip = (not offline and older_than > 0 and last
                and (today - dt.date.fromisoformat(last)).days < older_than)
        if not offline and not skip:
            try:
                if _refetch(scraper, year, records):
                    save_json(path, records)
                done[str(year)] = today.isoformat()
            except Exception as exc:  # keep going; the old counts stay
                logger.warning("[%s %s] fetch failed: %s", conference_id, year, exc)
                failed.append(f"{conference_id} {year}")
        elif offline:
            mtime = dt.date.fromtimestamp(path.stat().st_mtime).isoformat()
            done[str(year)] = min(done.get(str(year), mtime), mtime)

        counts = {str(r.get("articleNumber") or ""): citation_count(r)
                  for r in records if isinstance(r, dict) and r.get("articleNumber")}
        all_counts.update(counts)
        year_path = config.json_dir / f"{year}.json"
        if year_path.exists():
            data = load_json(year_path)
            papers = [p for s in data.get("sessions", []) for p in s.get("papers", [])]
            if _apply(papers, counts):
                save_json(year_path, data)
        save_json(META_PATH, meta)  # per year, so a killed run can resume
        logger.info("[%s %s] %d records", conference_id, year, len(counts))

    early_path = config.json_dir / "early_access.json"
    if early_path.exists():
        early = load_json(early_path)
        if isinstance(early, dict) and _apply(early.get("papers", []), all_counts):
            save_json(early_path, early)


def main(argv: Optional[List[str]] = None) -> int:
    setup_logging()
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sources", default="all", help="Comma-separated ids, or 'all'.")
    parser.add_argument("--offline", action="store_true",
                        help="Use the counts already in the record cache; no network.")
    parser.add_argument("--older-than", type=float, default=0, metavar="DAYS",
                        help="Skip years whose counts were fetched fewer than DAYS ago.")
    args = parser.parse_args(argv)

    sources = list(CONFERENCES) if args.sources == "all" else args.sources.split(",")
    meta = load_json(META_PATH) if META_PATH.exists() else {}
    failed: List[str] = []
    for conference_id in sources:
        refresh_source(conference_id.strip(), args.offline, args.older_than, meta, failed)
    if failed:
        logger.warning("Kept previous counts for %d year(s): %s", len(failed), ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
