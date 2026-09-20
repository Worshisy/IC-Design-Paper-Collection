"""
Fetch author affiliations for the whole corpus, newest papers first.

Affiliations are not in the search API; each paper needs its own request to
/rest/document/<articleNumber>/authors (~0.7 s). The full corpus is therefore
many hours of work, so this script is built to be stopped and resumed:

* Every lookup is cached in `cache/<source>/affiliations.json` and flushed
  every 50 fetches, so a kill loses at most 50 requests.
* Re-running only fetches what is still missing.
* Work is ordered by **year, newest first, across all sources at once** rather
  than source by source. Partial progress is then maximally useful: you get
  2026 everywhere before 2003 anywhere, instead of finishing ISSCC 2003 before
  touching JSSC 2026.

    python tools/backfill_affiliations.py                  # everything
    python tools/backfill_affiliations.py --from-year 2020 # recent only
    python tools/backfill_affiliations.py --budget 2000    # stop after N papers

Progress is written to `cache/affiliation_progress.json` so a later run (or a
person) can see how far it got.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import CONFERENCES, get_config  # noqa: E402
from scraper import Scraper  # noqa: E402
from utils import HttpError, save_json, setup_logging  # noqa: E402

logger = logging.getLogger("backfill")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROGRESS_PATH = PROJECT_ROOT / "cache" / "affiliation_progress.json"


def papers_missing_affiliations(json_dir: Path, year: int) -> int:
    """How many papers in one stored year still have no affiliations."""

    path = json_dir / f"{year}.json"
    if not path.exists():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    return sum(
        1
        for session in data.get("sessions", [])
        for paper in session.get("papers", [])
        if not paper.get("affiliations") and paper.get("article_number")
    )


def main() -> int:
    setup_logging()
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--from-year", type=int, default=1990,
                        help="Oldest year to touch (default: everything).")
    parser.add_argument("--to-year", type=int, default=dt.date.today().year + 1)
    parser.add_argument("--budget", type=int, default=0,
                        help="Stop after roughly this many papers (0 = no limit).")
    args = parser.parse_args()

    sources = list(CONFERENCES.keys())
    scrapers = {cid: Scraper(config=get_config(cid)) for cid in sources}

    # Survey first, so the log opens with the real size of the job.
    outstanding: dict[int, dict[str, int]] = {}
    for year in range(args.to_year, args.from_year - 1, -1):
        for cid in sources:
            missing = papers_missing_affiliations(scrapers[cid].config.json_dir, year)
            if missing:
                outstanding.setdefault(year, {})[cid] = missing

    total = sum(sum(v.values()) for v in outstanding.values())
    if not total:
        logger.info("Nothing to do: every stored paper already has affiliations.")
        return 0

    logger.info("=" * 64)
    logger.info("Affiliation backfill: %d papers across %d years", total, len(outstanding))
    logger.info("Roughly %.1f hours at ~1.1 s/paper. Safe to stop and resume.", total * 1.1 / 3600)
    logger.info("=" * 64)

    started = dt.datetime.now()
    done = 0
    for year in sorted(outstanding, reverse=True):
        for cid, missing in sorted(outstanding[year].items(), key=lambda kv: -kv[1]):
            if args.budget and done >= args.budget:
                logger.info("Budget of %d papers reached; stopping.", args.budget)
                _write_progress(started, done, total, year, cid)
                return 0

            scraper = scrapers[cid]
            logger.info(
                "[%s %s] %d papers missing (%d/%d done overall)",
                cid, year, missing, done, total,
            )
            try:
                updated = scraper.enrich_affiliations(start_year=year, end_year=year)
            except HttpError as exc:
                logger.error("[%s %s] giving up on this year: %s", cid, year, exc)
                continue
            except KeyboardInterrupt:
                logger.info("Interrupted; progress is cached.")
                _write_progress(started, done, total, year, cid)
                return 130

            done += updated
            _write_progress(started, done, total, year, cid)

    elapsed = dt.datetime.now() - started
    logger.info("Backfill complete: %d papers in %s.", done, str(elapsed).split(".")[0])
    return 0


def _write_progress(started: dt.datetime, done: int, total: int, year: int, source: str) -> None:
    save_json(
        PROGRESS_PATH,
        {
            "updated": dt.datetime.now().isoformat(timespec="seconds"),
            "started": started.isoformat(timespec="seconds"),
            "papers_done": done,
            "papers_total": total,
            "percent": round(100.0 * done / total, 1) if total else 100.0,
            "last_year": year,
            "last_source": source,
        },
    )


if __name__ == "__main__":
    raise SystemExit(main())
