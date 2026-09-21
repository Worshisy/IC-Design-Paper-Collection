"""
One-click database update: refresh -> validate -> build site -> sync to iCloud.

Run it from update.bat, or directly:

    python update_database.py                  # refresh recent years, all sources
    python update_database.py --full           # re-scrape every year from 2000
    python update_database.py --no-sync        # skip the iCloud copy
    python update_database.py --no-data        # sync the site but not output/
    python update_database.py --affiliations 400   # also fetch affiliations

What it does, in order:

1. Pulls annotations.json from iCloud and merges it into userdata/, so marks
   made on another machine survive.
2. Scrapes each source. By default only the last few years are re-fetched
   (that is where records still change); missing older years are filled in.
3. Validates and exports CSV/JSON.
4. Optionally fetches per-author affiliations, newest years first.
5. Rebuilds the static site and the master index.
6. Copies changed files to iCloud - the browsable site at the folder root,
   your marks under userdata/, and the dataset under output/. Only changed
   files are copied, so iCloud is not handed thousands of identical writes.

Your marks are never touched by steps 2-5: they live in userdata/annotations.json,
outside the scraped dataset.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import logging
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from config import CONFERENCES, get_config
from html_builder import (
    annotations_path,
    build_html_for_year_range,
    build_master_index,
    write_annotations_seed,
)
from scraper import Scraper
from utils import load_json, save_json, setup_logging
from validation import run_validation_and_exports

logger = logging.getLogger("update")

PROJECT_ROOT = Path(__file__).resolve().parent
ICLOUD_DEFAULT = Path.home() / "iCloudDrive" / "IC_Design_Materials" / "Paper_Collection"

# Years still being revised by IEEE. Older years are effectively frozen, so a
# routine update only re-fetches this window.
RECENT_YEARS = 2
# Default earliest year; a source can override it (config first_year).
FIRST_YEAR = 2000


# ----------------------------------------------------------------------
# Annotations (user data - never regenerated, only merged)
# ----------------------------------------------------------------------

def _merge_annotation_files(*sources: Path) -> Dict[str, Any]:
    """Merge annotation files, newest per-paper 'updated' timestamp winning."""

    merged: Dict[str, Any] = {}
    for src in sources:
        if not src or not src.exists():
            continue
        try:
            loaded = load_json(src)
        except (OSError, ValueError) as exc:
            logger.warning("Skipping unreadable annotations file %s: %s", src, exc)
            continue
        papers = loaded.get("papers") if isinstance(loaded, dict) else None
        if not isinstance(papers, dict):
            continue
        for paper_id, entry in papers.items():
            if not isinstance(entry, dict):
                continue
            current = merged.get(paper_id)
            if not current or str(entry.get("updated", "")) > str(current.get("updated", "")):
                merged[paper_id] = entry
    return merged


def sync_annotations_in(icloud_root: Path | None) -> int:
    """Pull marks from iCloud into userdata/ before anything else runs."""

    local = annotations_path()
    remote = (icloud_root / "userdata" / "annotations.json") if icloud_root else None
    merged = _merge_annotation_files(local, remote)

    # Only rewrite when the marks actually changed. Stamping a fresh timestamp
    # every run would alter this file and all nine annotations.js seeds, and
    # hand iCloud ten pointless writes on every update.
    existing: Dict[str, Any] = {}
    if local.exists():
        try:
            loaded = load_json(local)
            if isinstance(loaded, dict) and isinstance(loaded.get("papers"), dict):
                existing = loaded["papers"]
        except (OSError, ValueError):
            existing = {}

    if existing != merged:
        save_json(
            local,
            {"version": 1, "updated": dt.datetime.now().isoformat(), "papers": merged},
        )
        logger.info("Annotations: %d marked papers (updated).", len(merged))
    else:
        logger.info("Annotations: %d marked papers (unchanged).", len(merged))
    return len(merged)


# ----------------------------------------------------------------------
# Scrape / validate / build
# ----------------------------------------------------------------------

def years_to_refresh(
    cfg_json_dir: Path, full: bool, this_year: int, first_year: int = FIRST_YEAR
) -> Tuple[int, int, List[int]]:
    """
    Return (start, end, missing_years).

    Recent years are always re-fetched; older years only if their JSON is absent.
    first_year comes from the source's own config (JSSC starts at 1995).
    """

    end = this_year + 1
    if full:
        return first_year, end, []

    start = this_year - RECENT_YEARS
    present = {int(p.stem) for p in cfg_json_dir.glob("*.json") if p.stem.isdigit()}
    missing = [y for y in range(first_year, start) if y not in present]
    return start, end, missing


def update_source(
    conference_id: str,
    full: bool,
    this_year: int,
    affiliation_limit: int | None,
) -> None:
    cfg = get_config(conference_id)
    logger.info("=" * 62)
    logger.info("Source: %s", cfg.conference_name)
    logger.info("=" * 62)

    start, end, missing = years_to_refresh(cfg.json_dir, full, this_year, cfg.year_min)

    # Recent years: always re-fetch, records still change.
    Scraper(config=cfg, overwrite=True).scrape_year_range(start_year=start, end_year=end)

    # Older gaps: fetch once, then leave alone.
    if missing:
        logger.info("Filling %d missing older years: %s", len(missing), missing)
        gap_scraper = Scraper(config=cfg, overwrite=False)
        gap_scraper.scrape_year_range(start_year=min(missing), end_year=max(missing))

    if affiliation_limit:
        Scraper(config=cfg).enrich_affiliations(max_papers=affiliation_limit)

    run_validation_and_exports(json_dir=cfg.json_dir, csv_dir=cfg.csv_dir)


def build_site(conference_ids: Iterable[str]) -> None:
    site_root = PROJECT_ROOT / "site"
    for conference_id in conference_ids:
        cfg = get_config(conference_id)
        if not cfg.json_dir.exists():
            continue
        build_html_for_year_range(
            input_json_dir=cfg.json_dir,
            output_html_dir=cfg.html_dir,
            conference_name=cfg.conference_name,
        )
        write_annotations_seed(cfg.html_dir)
    build_master_index(site_root=site_root, conference_ids=list(CONFERENCES.keys()))


# ----------------------------------------------------------------------
# iCloud sync (last step, changed files only)
# ----------------------------------------------------------------------

def _digest(path: Path) -> str:
    h = hashlib.blake2b(digest_size=16)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# What we last copied to iCloud: destination path -> source content hash.
# Without it, deciding "has this changed?" means hashing the iCloud copy, and
# reading ~107 MB back out of iCloud takes minutes because files may be
# dehydrated placeholders that have to be downloaded first.
MANIFEST_PATH = PROJECT_ROOT / "cache" / "icloud_manifest.json"


def _load_manifest() -> Dict[str, str]:
    if not MANIFEST_PATH.exists():
        return {}
    try:
        loaded = load_json(MANIFEST_PATH)
        return loaded if isinstance(loaded, dict) else {}
    except (OSError, ValueError):
        return {}


def _needs_copy(src: Path, dst: Path, manifest: Dict[str, str], key: str) -> Tuple[bool, str]:
    """
    Decide whether to copy, without reading the iCloud copy back.

    The local hash is cheap; the remote one is not. A file is copied when we
    have no record of it, when the record disagrees with the local content, or
    when it is missing at the destination (a cheap stat, not a read).
    """

    digest = _digest(src)
    if manifest.get(key) != digest:
        return True, digest
    if not dst.exists():
        return True, digest
    return False, digest


# Where each local tree lands inside the iCloud folder. The browsable site
# goes to the ROOT, because that is the layout already in use there
# (Paper_Collection/isscc/..., Paper_Collection/index.html) - nesting it under
# "site/" would orphan every existing link and bookmark.
ICLOUD_LAYOUT = {
    "site": "",
    "userdata": "userdata",
    "output": "output",
}


def sync_to_icloud(icloud_root: Path, trees: Iterable[str]) -> Dict[str, int]:
    """Mirror the given project subtrees into iCloud, copying changed files only."""

    stats = {"copied": 0, "skipped": 0, "bytes": 0}
    icloud_root.mkdir(parents=True, exist_ok=True)
    manifest = _load_manifest()

    for tree in trees:
        src_root = PROJECT_ROOT / tree
        if not src_root.exists():
            continue
        destination = ICLOUD_LAYOUT.get(tree, tree)
        base = icloud_root / destination if destination else icloud_root
        for src in src_root.rglob("*"):
            if not src.is_file():
                continue
            relative = src.relative_to(src_root)
            dst = base / relative
            key = f"{destination}/{relative.as_posix()}" if destination else relative.as_posix()

            changed, digest = _needs_copy(src, dst, manifest, key)
            if changed:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                manifest[key] = digest
                stats["copied"] += 1
                stats["bytes"] += src.stat().st_size
            else:
                stats["skipped"] += 1

    save_json(MANIFEST_PATH, manifest)
    logger.info(
        "iCloud sync: %d changed files copied (%.1f MB), %d unchanged left alone.",
        stats["copied"], stats["bytes"] / 1_048_576, stats["skipped"],
    )
    return stats


# ----------------------------------------------------------------------

def main(argv: List[str] | None = None) -> int:
    setup_logging()
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--conference", default="all",
                        choices=list(CONFERENCES.keys()) + ["all"],
                        help="Limit the update to one source (default: all).")
    parser.add_argument("--full", action="store_true",
                        help=f"Re-scrape every year from {FIRST_YEAR} instead of just recent ones.")
    parser.add_argument("--affiliations", type=int, metavar="N", default=0,
                        help="Also fetch author affiliations for up to N papers per source.")
    parser.add_argument("--no-sync", action="store_true", help="Skip the iCloud copy.")
    parser.add_argument("--no-scrape", action="store_true",
                        help="Rebuild and sync from existing data without hitting the API.")
    parser.add_argument("--icloud-dir", type=Path, default=ICLOUD_DEFAULT,
                        help=f"iCloud destination (default: {ICLOUD_DEFAULT}).")
    parser.add_argument("--no-data", action="store_true",
                        help="Skip output/ (JSON+CSV); sync only the browsable site/ and your marks.")
    args = parser.parse_args(argv)

    started = dt.datetime.now()
    this_year = started.year
    ids = list(CONFERENCES.keys()) if args.conference == "all" else [args.conference]
    icloud_root = None if args.no_sync else args.icloud_dir

    # 1. Marks first, so nothing downstream can lose them.
    sync_annotations_in(icloud_root)

    # 2-4. Refresh the dataset.
    if not args.no_scrape:
        for conference_id in ids:
            try:
                update_source(conference_id, args.full, this_year, args.affiliations or None)
            except Exception as exc:  # one bad source must not stop the rest
                logger.exception("Source %s failed: %s", conference_id, exc)
    else:
        logger.info("--no-scrape: using existing JSON.")

    # 5. Rebuild the viewer.
    build_site(ids if args.conference != "all" else CONFERENCES.keys())

    # 6. Push to iCloud last, changed files only.
    if icloud_root:
        trees = ["site", "userdata"] + ([] if args.no_data else ["output"])
        sync_to_icloud(icloud_root, trees)
    else:
        logger.info("--no-sync: iCloud copy skipped.")

    logger.info("Done in %s.", str(dt.datetime.now() - started).split(".")[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
