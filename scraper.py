from __future__ import annotations

import logging
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import ScraperConfig, get_config
from parser import build_conference_year_from_api
from utils import HttpError, ensure_dir, load_json, retrying_post, save_json


logger = logging.getLogger(__name__)


class Scraper:
    """
    Scrapes IEEE conference proceedings via the IEEE Xplore REST search API.

    Instead of fetching rendered HTML (which requires JavaScript), this scraper
    uses the same JSON API that the IEEE Xplore frontend uses:
        POST https://ieeexplore.ieee.org/rest/search
    """

    def __init__(
        self,
        config: Optional[ScraperConfig] = None,
        *,
        force_refresh: bool = False,
        overwrite: bool = False,
    ) -> None:
        self.config: ScraperConfig = config or get_config()
        self.force_refresh: bool = force_refresh
        self.overwrite: bool = overwrite

    # ------------------------------------------------------------------
    # API helpers
    # ------------------------------------------------------------------

    def _search(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a search API call with rate limiting and retry."""

        time.sleep(self.config.rate_limit_seconds)
        return retrying_post(self.config.search_api_url, payload)

    @staticmethod
    def _normalize_title(text: str) -> str:
        return (text or "").lower().replace("-", " ")

    def _is_title_match(self, publication_title: str) -> bool:
        """
        Match a publication title against conference-specific include/exclude rules.
        """

        normalised = self._normalize_title(publication_title)
        includes = [self._normalize_title(x) for x in self.config.title_includes_any if x]
        excludes = [self._normalize_title(x) for x in self.config.title_excludes_any if x]

        if includes and not any(token in normalised for token in includes):
            return False
        if excludes and any(token in normalised for token in excludes):
            return False

        # Backward-compatible default behavior.
        want = self._normalize_title(self.config.title_contains)
        if want and want not in normalised:
            return False
        return True

    def _fetch_all_records_for_year(
        self, year: int, publication_number: str
    ) -> List[Dict[str, Any]]:
        """
        Page through the search API to get every record for one year's proceedings.

        Uses the 'punumber' field (not 'publicationNumber') to restrict results
        to exactly one conference year. Results are requested in vol-only-seq order
        so session headers and papers arrive in proceedings order.
        """

        all_records: List[Dict[str, Any]] = []
        page = 1
        total_pages = 1  # will be updated after first response

        while page <= total_pages:
            payload = {
                "newsearch": True,
                "queryText": "",
                "highlight": False,
                "returnType": "SEARCH",
                "matchPubs": True,
                "punumber": publication_number,
                "sortType": "vol-only-seq",
                "pageNumber": page,
                "rowsPerPage": self.config.rows_per_page,
            }
            # For journals (e.g., JSSC/TCAS-I), also restrict by publication year.
            if self.config.is_journal:
                payload["ranges"] = [f"{year}_{year}_Year"]

            logger.info(
                "[%s] Fetching page %s/%s (pubNumber=%s)",
                year, page, total_pages, publication_number,
            )

            data = self._search(payload)
            total_pages = data.get("totalPages", 1)
            records = data.get("records", [])
            all_records.extend(records)
            page += 1

        logger.info("[%s] Fetched %s records total", year, len(all_records))
        return all_records

    # ------------------------------------------------------------------
    # Year discovery
    # ------------------------------------------------------------------

    def discover_publication_number(self, year: int) -> Optional[str]:
        """
        Discover the IEEE Xplore publicationNumber for the configured conference year.

        Uses the conference's search_term and checks publication title against
        title_contains (normalised: lowercase, hyphens to spaces).
        """

        query_terms = self.config.search_terms or [self.config.search_term]
        for query in query_terms:
            payload = {
                "newsearch": True,
                "queryText": query,
                "highlight": False,
                "returnType": "SEARCH",
                "matchPubs": True,
                "ranges": [f"{year}_{year}_Year"],
                "refinements": ["ContentType:Conferences"],
                "pageNumber": 1,
                "rowsPerPage": 50,
            }

            try:
                data = self._search(payload)
            except HttpError:
                logger.warning("Search failed for year %s (query=%r)", year, query)
                continue

            records = data.get("records", [])
            if not records:
                continue

            for rec in records:
                pub_title = rec.get("publicationTitle", "")
                if not self._is_title_match(pub_title):
                    continue

                pub_number = rec.get("publicationNumber")
                if pub_number:
                    logger.info(
                        "[%s] Discovered publicationNumber=%s  (%s)",
                        year, pub_number, pub_title,
                    )
                    return str(pub_number)

        return None

    def discover_available_years(
        self,
        start_year: Optional[int] = None,
        end_year: Optional[int] = None,
    ) -> Dict[int, str]:
        """
        Return a mapping of year -> publicationNumber for all available years.

        For conferences with year_to_pubs (hardcoded multi-pub mapping), uses
        a comma-separated string of publication numbers as the value so that
        scrape_year can fetch from multiple pubs and merge.
        """

        start = start_year or self.config.year_min
        end = end_year or 2030

        # Hardcoded year→pub mapping (e.g. VLSI with Circuits+Technology tracks).
        if self.config.year_to_pubs:
            year_to_pub: Dict[int, str] = {}
            for year in range(start, end + 1):
                pubs = self.config.year_to_pubs.get(year)
                if pubs:
                    year_to_pub[year] = ",".join(pubs)
            logger.info(
                "Using hardcoded year_to_pubs for %s: %d years in range %s–%s",
                self.config.conference_name, len(year_to_pub), start, end,
            )
            return year_to_pub

        # Journals have a fixed publication number. Years are identified by the
        # publicationYear filter (ranges).
        if self.config.is_journal and self.config.fixed_punumber:
            pub = str(self.config.fixed_punumber)
            year_to_pub = {year: pub for year in range(start, end + 1)}
            logger.info(
                "Using fixed punumber=%s for %s across years %s–%s",
                pub,
                self.config.conference_name,
                start,
                end,
            )
            return year_to_pub

        year_to_pub = {}

        for year in range(start, end + 1):
            pub_number = self.discover_publication_number(year)
            if pub_number:
                year_to_pub[year] = pub_number

        logger.info("Discovered %d %s proceedings years", len(year_to_pub), self.config.conference_name)
        return year_to_pub

    # ------------------------------------------------------------------
    # Year-level scraping
    # ------------------------------------------------------------------

    def _year_json_path(self, year: int) -> Path:
        return self.config.json_dir / f"{year}.json"

    def _year_error_path(self, year: int) -> Path:
        return self.config.json_dir / f"{year}_errors.json"

    def _early_access_json_path(self) -> Path:
        return self.config.json_dir / "early_access.json"

    @staticmethod
    def _is_early_issue_session(session_name: str) -> bool:
        lower = (session_name or "").lower()
        return (
            "early access" in lower
            or "vol. pp" in lower
            or "issue 99" in lower
        )

    def _extract_early_access_from_year_data(
        self,
        year: int,
        year_data: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        For journal-style years (JSSC), remove Early Access sessions from the
        per-year structure and return those papers as a flat list.
        """

        sessions = year_data.get("sessions", [])
        keep_sessions: List[Dict[str, Any]] = []
        early_papers: List[Dict[str, Any]] = []

        for session in sessions:
            session_name = session.get("session_name", "")
            papers = session.get("papers", [])
            if self._is_early_issue_session(session_name):
                for p in papers:
                    early_papers.append(
                        {
                            "year": year,
                            "title": p.get("title", ""),
                            "abstract": p.get("abstract", ""),
                            "authors": p.get("authors", []),
                            "paper_url": p.get("paper_url") or "",
                            "doi": p.get("doi"),
                            "conference_name": p.get("conference_name"),
                            "conference_dates": p.get("conference_dates"),
                        }
                    )
            else:
                keep_sessions.append(session)

        if not early_papers:
            return []

        # Re-number remaining sessions and paper numbers to keep contiguous ordering.
        for new_session_idx, session in enumerate(keep_sessions, start=1):
            old_session_name = session.get("session_name", "")
            session["session_number"] = new_session_idx
            session["session_code"] = str(new_session_idx)
            papers = session.get("papers", [])
            for paper_idx, paper in enumerate(papers, start=1):
                new_num = f"{new_session_idx}.{paper_idx}"
                paper["session_number"] = new_session_idx
                paper["session_name"] = old_session_name
                paper["paper_number"] = new_num
                paper["inferred_paper_number"] = new_num

        year_data["sessions"] = keep_sessions
        return early_papers

    def scrape_year(self, year: int, publication_number: str) -> Dict[str, Any]:
        """
        Scrape all papers for a single conference year via the search API.

        publication_number may be comma-separated (e.g. "6880,6881") for
        conferences with multiple tracks per year (VLSI Circuits + Technology).
        Records from all pubs are merged before parsing.

        Returns the year JSON structure as a Python dictionary.
        """

        year_path = self._year_json_path(year)
        errors_path = self._year_error_path(year)

        # Resumability: if a JSON already exists, skip unless overwrite.
        if year_path.exists() and not self.overwrite:
            logger.info("[%s] Loading existing JSON from %s", year, year_path)
            return load_json(year_path)

        errors: List[Dict[str, Any]] = []
        pub_numbers = [p.strip() for p in publication_number.split(",") if p.strip()]
        primary_pub = pub_numbers[0]

        if self.config.is_journal:
            proceedings_url = f"{self.config.base_url}/xpl/issues?punumber={primary_pub}"
        else:
            proceedings_url = f"{self.config.base_url}/xpl/conhome/{primary_pub}/proceeding"

        records: List[Dict[str, Any]] = []
        for pub in pub_numbers:
            try:
                part = self._fetch_all_records_for_year(year, pub)
                records.extend(part)
            except HttpError as exc:
                logger.error("[%s] Failed to fetch records for pub %s: %s", year, pub, exc)
                errors.append({"year": year, "pub": pub, "reason": str(exc)})

        if not records:
            save_json(errors_path, errors)
            return {}

        year_model = build_conference_year_from_api(
            records=records,
            year=year,
            proceedings_url=proceedings_url,
            publication_number=primary_pub,
            group_by_issue=bool(self.config.is_journal),
        )

        year_data = asdict(year_model)
        save_json(year_path, year_data)

        # Log summary.
        total_papers = sum(len(s.papers) for s in year_model.sessions)
        logger.info(
            "[%s] Parsed %s sessions, %s papers",
            year, len(year_model.sessions), total_papers,
        )

        # Report papers missing key data.
        for session in year_model.sessions:
            for paper in session.papers:
                if not paper.abstract:
                    errors.append({
                        "year": year,
                        "paper_number": paper.paper_number,
                        "title": paper.title,
                        "issue": "missing abstract",
                    })
                if not paper.authors:
                    errors.append({
                        "year": year,
                        "paper_number": paper.paper_number,
                        "title": paper.title,
                        "issue": "missing authors",
                    })

                logger.info(
                    "[%s] session %s paper %s OK",
                    year, session.session_number, paper.paper_number,
                )

        save_json(errors_path, errors)
        return year_data

    # ------------------------------------------------------------------
    # Public workflow
    # ------------------------------------------------------------------

    def scrape_year_range(
        self,
        start_year: Optional[int] = None,
        end_year: Optional[int] = None,
    ) -> None:
        """Scrape all conference years in the given inclusive range."""

        available = self.discover_available_years(
            start_year=start_year,
            end_year=end_year,
        )
        if not available:
            logger.error("No %s proceedings discovered; aborting.", self.config.conference_name)
            return

        all_early_access: List[Dict[str, Any]] = []

        for year in sorted(available):
            pub_number = available[year]
            logger.info("=== Scraping year %s (pubNumber=%s) ===", year, pub_number)
            year_data = self.scrape_year(year, pub_number)

            # Journal post-processing: keep Early Access separate from regular
            # year/issues.
            if self.config.is_journal and year_data:
                early = self._extract_early_access_from_year_data(year, year_data)
                if early:
                    all_early_access.extend(early)
                    save_json(self._year_json_path(year), year_data)
                    logger.info(
                        "[%s] Moved %d Early Access papers to separate collection",
                        year, len(early),
                    )

        if self.config.is_journal:
            payload = {
                "conference_name": self.config.conference_name,
                "label": "Early Access",
                "papers": all_early_access,
            }
            save_json(self._early_access_json_path(), payload)
            logger.info("Saved %d Early Access papers to %s", len(all_early_access), self._early_access_json_path())


__all__ = ["Scraper"]
