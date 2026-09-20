from __future__ import annotations

import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import ScraperConfig, get_config
from parser import build_conference_year_from_api
from utils import HttpError, load_json, retrying_get, retrying_post, save_json


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
        """Execute a search API call. Pacing and retry live in utils."""

        return retrying_post(
            self.config.search_api_url, payload, self.config.rate_limit_seconds
        )

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
            self._apply_pub_overrides(year_to_pub, start, end)
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
            self._apply_pub_overrides(year_to_pub, start, end)
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

        self._apply_pub_overrides(year_to_pub, start, end)
        logger.info("Discovered %d %s proceedings years", len(year_to_pub), self.config.conference_name)
        return year_to_pub

    def _apply_pub_overrides(self, year_to_pub: Dict[int, str], start: int, end: int) -> None:
        """Pin years the search cannot find (see year_pub_overrides in config)."""

        for year, pubs in self.config.year_pub_overrides.items():
            if start <= year <= end and pubs:
                year_to_pub[year] = ",".join(str(pub) for pub in pubs)
                logger.info("[%s] Using configured publication override %s", year, pubs)

    # ------------------------------------------------------------------
    # Year-level scraping
    # ------------------------------------------------------------------

    def _year_json_path(self, year: int) -> Path:
        return self.config.json_dir / f"{year}.json"

    def _year_error_path(self, year: int) -> Path:
        return self.config.json_dir / f"{year}_errors.json"

    def _early_access_json_path(self) -> Path:
        return self.config.json_dir / "early_access.json"

    def _records_cache_path(self, year: int) -> Path:
        """Raw API records for one year, kept so re-parsing needs no network."""

        return self.config.cache_dir / "records" / f"{year}.json"

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
        failed_pubs: List[str] = []
        for pub in pub_numbers:
            try:
                part = self._fetch_all_records_for_year(year, pub)
                records.extend(part)
            except HttpError as exc:
                logger.error("[%s] Failed to fetch records for pub %s: %s", year, pub, exc)
                errors.append({"year": year, "pub": pub, "reason": str(exc)})
                failed_pubs.append(pub)

        # Conferences with several tracks per year (VLSI) would otherwise store a
        # half-year when one track fails. Keep whatever is already on disk.
        if failed_pubs:
            logger.error(
                "[%s] %d of %d publications failed; leaving existing JSON untouched.",
                year, len(failed_pubs), len(pub_numbers),
            )
            save_json(errors_path, errors)
            return {}

        if not records:
            save_json(errors_path, errors)
            return {}

        # Keep the raw records: parser changes can then be re-applied offline
        # with reparse_year(), instead of re-fetching everything from IEEE.
        save_json(self._records_cache_path(year), records)

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

                logger.debug(
                    "[%s] session %s paper %s OK",
                    year, session.session_number, paper.paper_number,
                )

        save_json(errors_path, errors)
        return year_data

    def _save_early_access(
        self,
        early_papers: List[Dict[str, Any]],
        scraped_years: set[int],
    ) -> None:
        """
        Merge this run's Early Access papers into the shared collection.

        Only entries belonging to the years this run actually scraped are
        replaced, so scraping a single year never drops the other years.
        """

        path = self._early_access_json_path()
        merged: Dict[str, Dict[str, Any]] = {}

        if path.exists():
            try:
                prior = load_json(path)
                for paper in prior.get("papers", []):
                    try:
                        paper_year = int(paper.get("year", 0) or 0)
                    except (TypeError, ValueError):
                        paper_year = 0
                    if paper_year in scraped_years:
                        continue  # re-fetched this run; drop the stale copy
                    key = paper.get("paper_url") or paper.get("title", "")
                    if key:
                        merged[key] = paper
            except (OSError, ValueError) as exc:
                logger.warning("Early Access file unreadable, rebuilding: %s", exc)

        for paper in early_papers:
            key = paper.get("paper_url") or paper.get("title", "")
            if key:
                merged[key] = paper

        papers = sorted(
            merged.values(),
            key=lambda p: (-int(p.get("year", 0) or 0), p.get("title", "")),
        )
        save_json(
            path,
            {
                "conference_name": self.config.conference_name,
                "label": "Early Access",
                "papers": papers,
            },
        )
        logger.info(
            "Early Access: %d from this run, %d total after merge -> %s",
            len(early_papers), len(papers), path,
        )

    def reparse_year(self, year: int) -> bool:
        """
        Rebuild one year's JSON from cached raw records, with no network use.

        Returns False when that year has no cached records yet.
        """

        cache_path = self._records_cache_path(year)
        if not cache_path.exists():
            return False

        try:
            records = load_json(cache_path)
        except (OSError, ValueError) as exc:
            logger.warning("[%s] Unreadable record cache: %s", year, exc)
            return False
        if not records:
            return False

        pubs = self.config.year_to_pubs.get(year) or []
        primary_pub = str(pubs[0]) if pubs else str(self.config.fixed_punumber or "")
        if self.config.is_journal:
            proceedings_url = f"{self.config.base_url}/xpl/issues?punumber={primary_pub}"
        else:
            proceedings_url = f"{self.config.base_url}/xpl/conhome/{primary_pub}/proceeding"

        year_model = build_conference_year_from_api(
            records=records,
            year=year,
            proceedings_url=proceedings_url,
            publication_number=primary_pub,
            group_by_issue=bool(self.config.is_journal),
        )
        year_data = asdict(year_model)
        save_json(self._year_json_path(year), year_data)
        logger.info(
            "[%s] Re-parsed from cache: %d sessions, %d papers",
            year, len(year_model.sessions),
            sum(len(sess.papers) for sess in year_model.sessions),
        )
        return True

    def reparse_all(self) -> int:
        """Re-parse every cached year for this source. Returns years rebuilt."""

        cache_dir = self.config.cache_dir / "records"
        if not cache_dir.is_dir():
            logger.warning(
                "%s: no cached records yet - run a scrape once to populate them.",
                self.config.conference_name,
            )
            return 0

        years = sorted(int(p.stem) for p in cache_dir.glob("*.json") if p.stem.isdigit())
        rebuilt = 0
        all_early: List[Dict[str, Any]] = []
        for year in years:
            if self.reparse_year(year):
                rebuilt += 1
                if self.config.is_journal:
                    year_data = load_json(self._year_json_path(year))
                    early = self._extract_early_access_from_year_data(year, year_data)
                    if early:
                        all_early.extend(early)
                        save_json(self._year_json_path(year), year_data)

        if self.config.is_journal and years:
            self._save_early_access(all_early, scraped_years=set(years))

        logger.info("%s: re-parsed %d cached years.", self.config.conference_name, rebuilt)
        return rebuilt

    # ------------------------------------------------------------------
    # Author affiliations (one extra request per paper)
    # ------------------------------------------------------------------

    def _affiliation_cache_path(self) -> Path:
        return self.config.cache_dir / "affiliations.json"

    def _fetch_author_affiliations(self, article_number: str) -> Optional[List[str]]:
        """
        Return affiliations index-aligned with the document author list.

        The search API omits affiliations entirely; only the per-document
        authors endpoint carries them.
        """

        url = f"{self.config.base_url}/rest/document/{article_number}/authors"
        data = retrying_get(url, self.config.affiliation_rate_limit_seconds)
        authors = data.get("authors")
        if not isinstance(authors, list):
            return None

        affiliations: List[str] = []
        for author in authors:
            affiliation = author.get("affiliation") or []
            if isinstance(affiliation, str):
                affiliation = [affiliation]
            affiliations.append("; ".join(a for a in affiliation if a))
        return affiliations

    def enrich_affiliations(
        self,
        start_year: Optional[int] = None,
        end_year: Optional[int] = None,
        max_papers: Optional[int] = None,
    ) -> int:
        """
        Fill in per-author affiliations for stored years, newest year first.

        Resumable: every lookup is cached in cache/<id>/affiliations.json, so
        re-running only fetches papers still missing. Returns papers updated.
        """

        cache: Dict[str, Any] = {}
        cache_path = self._affiliation_cache_path()
        if cache_path.exists():
            try:
                cache = load_json(cache_path)
            except (OSError, ValueError):
                logger.warning("Affiliation cache unreadable; starting fresh.")

        year_paths = sorted(
            (p for p in self.config.json_dir.glob("*.json") if p.stem.isdigit()),
            key=lambda p: int(p.stem),
            reverse=True,
        )

        updated = 0
        fetched_since_save = 0
        for path in year_paths:
            year = int(path.stem)
            if start_year is not None and year < start_year:
                continue
            if end_year is not None and year > end_year:
                continue

            year_data = load_json(path)
            year_changed = False

            for session in year_data.get("sessions", []):
                for paper in session.get("papers", []):
                    if max_papers is not None and updated >= max_papers:
                        break
                    if paper.get("affiliations"):
                        continue
                    article_number = paper.get("article_number")
                    if not article_number:
                        continue

                    if article_number in cache:
                        affiliations = cache[article_number]
                    else:
                        try:
                            affiliations = self._fetch_author_affiliations(article_number)
                        except HttpError as exc:
                            logger.warning(
                                "[%s] affiliation fetch failed for %s: %s",
                                year, article_number, exc,
                            )
                            continue
                        cache[article_number] = affiliations
                        fetched_since_save += 1
                        if fetched_since_save >= 50:
                            save_json(cache_path, cache)
                            fetched_since_save = 0

                    if not affiliations:
                        continue

                    paper["affiliations"] = affiliations
                    paper["author_affiliations_raw"] = "; ".join(
                        dict.fromkeys(a for a in affiliations if a)
                    )
                    updated += 1
                    year_changed = True

                if max_papers is not None and updated >= max_papers:
                    break

            if year_changed:
                save_json(path, year_data)
                logger.info("[%s] affiliations written (%d papers updated so far)", year, updated)

            if max_papers is not None and updated >= max_papers:
                logger.info("Reached max_papers=%s; stopping.", max_papers)
                break

        save_json(cache_path, cache)
        logger.info(
            "Affiliation enrichment complete: %d papers updated, %d cached.",
            updated, len(cache),
        )
        return updated

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

        failed_years: List[int] = []
        for year in sorted(available):
            pub_number = available[year]
            logger.info("=== Scraping year %s (pubNumber=%s) ===", year, pub_number)
            try:
                year_data = self.scrape_year(year, pub_number)
            except HttpError as exc:
                # Transient upstream failure: keep the year that is already on
                # disk and carry on with the rest of the range.
                logger.error("[%s] Skipped after repeated API failures: %s", year, exc)
                failed_years.append(year)
                continue

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
            # Only merge over years this run actually managed to fetch.
            self._save_early_access(
                all_early_access,
                scraped_years=set(available) - set(failed_years),
            )

        if failed_years:
            logger.warning(
                "%s: %d year(s) could not be fetched and were left unchanged: %s",
                self.config.conference_name, len(failed_years), failed_years,
            )


__all__ = ["Scraper"]
