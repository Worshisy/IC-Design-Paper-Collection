from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, Optional, List

# Conference definitions: id -> { name, search_term, title_contains }
# title_contains: substring (normalized to lowercase, hyphens→spaces) that must appear in publication title.
CONFERENCES: Dict[str, Dict[str, Any]] = {
    "isscc": {
        "name": "ISSCC",
        "search_term": "ISSCC",
        "title_contains": "solid state circuits conference",
    },
    "rfic": {
        "name": "RFIC",
        "search_term": "RFIC",
        "title_contains": "radio frequency integrated",
    },
    "cicc": {
        "name": "CICC",
        "search_term": "CICC",
        "title_contains": "custom integrated circuits",
    },
    "jssc": {
        "name": "JSSC",
        "search_term": "JSSC",
        "title_contains": "journal of solid-state circuits",
        "is_journal": True,
        "fixed_punumber": "4",
    },
    "sscl": {
        "name": "SSCL",
        "search_term": "SSCL",
        "title_contains": "solid-state circuits letters",
        "is_journal": True,
        "fixed_punumber": "8011414",
    },
    "tcas1": {
        "name": "TCAS-I",
        "search_term": "TCAS-I",
        "title_contains": "transactions on circuits and systems i",
        "is_journal": True,
        "fixed_punumber": "8919",
    },
    "tcas2": {
        "name": "TCAS-II",
        "search_term": "TCAS-II",
        "title_contains": "transactions on circuits and systems ii",
        "is_journal": True,
        "fixed_punumber": "8920",
    },
    "tmtt": {
        "name": "TMTT",
        "search_term": "TMTT",
        "title_contains": "transactions on microwave theory and techniques",
        "is_journal": True,
        "fixed_punumber": "22",
    },
    "vlsi": {
        "name": "VLSI",
        "search_term": "Symposium on VLSI Technology and Circuits",
        "title_contains": "symposium on vlsi",
        "year_to_pubs": {
            2000: ["6880", "6881"],
            2001: ["7437", "7441"],
            2002: ["7919", "7925"],
            2003: ["8656", "8657"],
            2004: ["9331", "9327"],
            2005: ["9912", "9911"],
            2006: ["11174", "11173"],
            2007: ["4342660", "4339664"],
            2008: ["4573021", "4573020"],
            2009: ["5176049", "5176122"],
            2010: ["5552635", "5548927"],
            2011: ["5976946", "5976318"],
            2012: ["6235082", "6235083"],
            2013: ["6571720", "6571719"],
            2014: ["6850260", "6886509"],
            2015: ["7196579", "7198535"],
            2016: ["7569797", "7569798"],
            2017: ["8000695", "7989855"],
            2018: ["8484863", "8481640"],
            2019: ["8766307", "8766306"],
            2020: ["9146894", "9264988"],
            2021: ["9492225", "9508626"],
            2022: ["9830116"],
            2023: ["10185199"],
            2024: ["10631290"],
            2025: ["11074776"],
        },
    },
}


@dataclass(slots=True)
class ScraperConfig:
    """Configuration for the IEEE proceedings scraper."""

    conference_id: str = "isscc"
    base_url: str = "https://ieeexplore.ieee.org"
    search_api_url: str = "https://ieeexplore.ieee.org/rest/search"
    year_min: int = 2000

    # Conference-specific (set by get_config from CONFERENCES).
    conference_name: str = "ISSCC"
    search_term: str = "ISSCC"
    title_contains: str = "solid state circuits conference"
    is_journal: bool = False
    fixed_punumber: Optional[str] = None
    search_terms: List[str] = field(default_factory=list)
    title_includes_any: List[str] = field(default_factory=list)
    title_excludes_any: List[str] = field(default_factory=list)
    year_to_pubs: Dict[int, List[str]] = field(default_factory=dict)

    # HTTP behaviour
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0 Safari/537.36"
    )
    request_timeout_seconds: int = 30
    # IEEE answers sustained scraping with intermittent 502s, so retries are
    # patient: 8 attempts backing off to 2 minutes rides out a throttle window.
    max_retries: int = 8
    backoff_initial_seconds: float = 3.0
    backoff_max_seconds: float = 120.0
    rate_limit_seconds: float = 1.5
    # The per-document authors endpoint is one call per paper, so it gets a
    # shorter delay than the search API to keep backfills tractable.
    affiliation_rate_limit_seconds: float = 0.4
    rows_per_page: int = 100

    # Adaptive pacing, applied globally across every IEEE request.
    # On a 5xx/429 the floor doubles (up to rate_limit_ceiling_seconds) and
    # decays back after a run of clean responses, so a slow patch throttles
    # the whole scrape instead of hammering through it.
    rate_limit_jitter: float = 0.3
    rate_limit_ceiling_seconds: float = 45.0
    rate_limit_recovery_successes: int = 12
    # After this many consecutive failures, pause outright rather than burn
    # retries against an endpoint that is clearly refusing us.
    circuit_break_failures: int = 6
    circuit_break_cooldown_seconds: float = 300.0
    circuit_break_max_cooldowns: int = 3

    # Paths (set by get_config from project_root + conference_id)
    project_root: Path = field(default_factory=lambda: Path(__file__).resolve().parent)
    cache_dir: Path = field(default_factory=Path)
    raw_html_dir: Path = field(default_factory=Path)
    json_dir: Path = field(default_factory=Path)
    csv_dir: Path = field(default_factory=Path)
    html_dir: Path = field(default_factory=Path)


def get_config(conference_id: str = "isscc", create_dirs: bool = True) -> ScraperConfig:
    """
    Return a ScraperConfig for the given conference.

    create_dirs=False is for callers that only need paths (e.g. the shared
    HTTP session), so merely importing a module never creates directories
    for a conference the user did not ask for.
    """

    conf = CONFERENCES.get(conference_id)
    if not conf:
        conf = CONFERENCES["isscc"]
        conference_id = "isscc"

    root = Path(__file__).resolve().parent
    cache = root / "cache" / conference_id
    cfg = ScraperConfig(
        conference_id=conference_id,
        conference_name=conf["name"],
        search_term=conf["search_term"],
        title_contains=conf["title_contains"],
        is_journal=bool(conf.get("is_journal", False)),
        fixed_punumber=conf.get("fixed_punumber"),
        search_terms=list(conf.get("search_terms", [])),
        title_includes_any=list(conf.get("title_includes_any", [])),
        title_excludes_any=list(conf.get("title_excludes_any", [])),
        year_to_pubs=dict(conf.get("year_to_pubs", {})),
        project_root=root,
        cache_dir=cache,
        raw_html_dir=cache / "raw_html",
        json_dir=root / "output" / conference_id / "json",
        csv_dir=root / "output" / conference_id / "csv",
        html_dir=root / "site" / conference_id,
    )

    if create_dirs:
        for directory in (cfg.cache_dir, cfg.json_dir, cfg.csv_dir, cfg.html_dir):
            directory.mkdir(parents=True, exist_ok=True)

    return cfg
