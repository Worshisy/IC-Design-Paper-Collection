from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Optional

from config import CONFERENCES, get_config
from scraper import Scraper
from validation import run_validation_and_exports
from utils import setup_logging


logger = logging.getLogger(__name__)

CONFERENCE_CHOICES = list(CONFERENCES.keys()) + ["all"]


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape IEEE Xplore proceedings/journals (ISSCC, RFIC, CICC, JSSC, SSCL, TCAS-I, TCAS-II, TMTT, VLSI) and build local datasets.",
    )
    parser.add_argument(
        "--conference",
        choices=CONFERENCE_CHOICES,
        default="isscc",
        help="Source to scrape/build (e.g. isscc, rfic, cicc, jssc, sscl, tcas1) or all (default: isscc).",
    )
    parser.add_argument(
        "--start-year",
        type=int,
        help="First year (inclusive) to scrape. Defaults to earliest discovered year >= configured minimum.",
    )
    parser.add_argument(
        "--end-year",
        type=int,
        help="Last year (inclusive) to scrape. Defaults to latest discovered year.",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Re-fetch every selected year from the API, ignoring existing JSON (implies --overwrite).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing per-year JSON instead of resuming enrichment.",
    )
    parser.add_argument(
        "--build-html-only",
        action="store_true",
        help="Do not scrape; only build static HTML from existing JSON files.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate existing JSON and export CSVs without scraping.",
    )
    parser.add_argument(
        "--export-only",
        action="store_true",
        help="Alias for --validate-only (kept for readability).",
    )
    parser.add_argument(
        "--reparse",
        action="store_true",
        help=(
            "Rebuild JSON from cached raw records without touching the network. "
            "Use after changing parser rules."
        ),
    )
    parser.add_argument(
        "--toc-sessions",
        action="store_true",
        help=(
            "Rebuild sessions from each year's printed programme (Table of "
            "Contents PDF). Recovers real session names for RFIC/CICC/VLSI, "
            "which expose none through the search API."
        ),
    )
    parser.add_argument(
        "--enrich-affiliations",
        action="store_true",
        help=(
            "Fetch per-author affiliations for stored years (newest first). "
            "One extra request per paper; resumable via cache/<id>/affiliations.json."
        ),
    )
    parser.add_argument(
        "--affiliation-limit",
        type=int,
        help="Stop affiliation enrichment after this many papers per source.",
    )
    parser.add_argument(
        "--input-json-dir",
        type=str,
        help="Directory containing per-year JSON files (defaults to configured output/<conference>/json).",
    )
    return parser.parse_args(argv)


def _conference_ids(conference_arg: str) -> list[str]:
    """Return list of conference ids to run (excluding 'all')."""
    if conference_arg == "all":
        return list(CONFERENCES.keys())
    return [conference_arg]


def main(argv: Optional[list[str]] = None) -> int:
    setup_logging()
    args = parse_args(argv)
    ids = _conference_ids(args.conference)

    if args.build_html_only:
        try:
            from html_builder import build_html_for_year_range, build_master_index
        except ImportError:
            logger.error(
                "--build-html-only was requested but html_builder is not available."
            )
            return 1

        for cid in ids:
            cfg = get_config(cid)
            input_dir = Path(args.input_json_dir) if args.input_json_dir else cfg.json_dir
            if not input_dir.exists():
                logger.warning("Input JSON directory does not exist for %s: %s", cid, input_dir)
                continue
            build_html_for_year_range(
                input_json_dir=input_dir,
                output_html_dir=cfg.html_dir,
                start_year=args.start_year,
                end_year=args.end_year,
                conference_name=cfg.conference_name,
            )

        if args.conference == "all":
            site_root = get_config(ids[0]).project_root / "site"
            build_master_index(site_root=site_root, conference_ids=list(CONFERENCES.keys()))
        return 0

    if args.reparse:
        for cid in ids:
            cfg = get_config(cid)
            logger.info("=== Re-parsing cached records: %s ===", cfg.conference_name)
            Scraper(config=cfg).reparse_all()
            run_validation_and_exports(json_dir=cfg.json_dir, csv_dir=cfg.csv_dir)
        return 0

    if args.toc_sessions:
        for cid in ids:
            cfg = get_config(cid)
            logger.info("=== Programme sessions: %s ===", cfg.conference_name)
            Scraper(config=cfg).enrich_sessions_all(
                start_year=args.start_year, end_year=args.end_year
            )
            run_validation_and_exports(json_dir=cfg.json_dir, csv_dir=cfg.csv_dir)
        return 0

    if args.enrich_affiliations:
        for cid in ids:
            cfg = get_config(cid)
            logger.info("=== Affiliations: %s ===", cfg.conference_name)
            scraper = Scraper(config=cfg)
            scraper.enrich_affiliations(
                start_year=args.start_year,
                end_year=args.end_year,
                max_papers=args.affiliation_limit,
            )
            run_validation_and_exports(json_dir=cfg.json_dir, csv_dir=cfg.csv_dir)
        return 0

    if args.validate_only or args.export_only:
        for cid in ids:
            cfg = get_config(cid)
            input_dir = Path(args.input_json_dir) if args.input_json_dir else cfg.json_dir
            if not input_dir.exists():
                logger.warning("JSON directory does not exist for %s: %s", cid, input_dir)
                continue
            run_validation_and_exports(
                json_dir=input_dir,
                csv_dir=cfg.csv_dir,
            )
        return 0

    # Scrape + validate
    for cid in ids:
        cfg = get_config(cid)
        logger.info("=== Conference: %s ===", cfg.conference_name)
        scraper = Scraper(
            config=cfg,
            force_refresh=bool(args.force_refresh),
            overwrite=bool(args.overwrite or args.force_refresh),
        )
        scraper.scrape_year_range(
            start_year=args.start_year,
            end_year=args.end_year,
        )
        run_validation_and_exports(
            json_dir=cfg.json_dir,
            csv_dir=cfg.csv_dir,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
