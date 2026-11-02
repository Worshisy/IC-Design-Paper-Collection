from __future__ import annotations

import copy
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Set

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
                            "article_number": p.get("article_number"),
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

        # What the cache held before this fetch, so a paper that is genuinely
        # new can be told from one the saved programme deliberately excluded.
        previous_articles = self.cached_article_numbers(year)

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

        # Raw records carry no session structure, no track split, no overrides
        # and no affiliations, so a scrape would otherwise throw away every
        # programme pass this year has had. The year file on disk is still the
        # old one at this point, which is what the restore reads - doing this
        # after the write instead silently loses the lot.
        fetched = {
            str(paper.get("article_number") or "")
            for session in year_data.get("sessions", [])
            for paper in session.get("papers", [])
        }
        self._restore_session_layout(
            year, year_data, keep_articles=fetched - previous_articles
        )
        self._apply_track_filter(year, year_data)
        self._apply_session_overrides(year, year_data)
        self._restore_full_abstracts(year_data)  # [c]
        if self.config.is_journal:
            # The Early Access pseudo-issue belongs in its own collection, not
            # in the year. Done here so the year file is written exactly once.
            self._save_early_access(
                self._extract_early_access_from_year_data(year, year_data),
                scraped_years={year},
            )
        save_json(year_path, year_data)
        # Records carry no affiliations; re-apply this year's from cache, or a
        # refresh blanks every one of them.
        self.enrich_affiliations(start_year=year, end_year=year, cache_only=True)

        # Log summary. Counted from what was written, not from year_model:
        # the session layout, track split and overrides all change the shape
        # after parsing, and reporting the raw parse reads like a regression.
        saved_sessions = year_data.get("sessions", [])
        total_papers = sum(len(s.get("papers", [])) for s in saved_sessions)
        logger.info(
            "[%s] Saved %s sessions, %s papers",
            year, len(saved_sessions), total_papers,
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

    def _restore_session_layout(
        self,
        year: int,
        year_data: Dict[str, Any],
        keep_articles: Optional[Set[str]] = None,
    ) -> bool:
        """
        Re-apply the session grouping a previous programme pass worked out.

        Re-parsing rebuilds a year from raw records, which carry no session
        structure, so without this the table-of-contents work is thrown away -
        the reason --reparse used to have to run before --toc-sessions.
        """

        if self.config.is_journal:
            return False
        path = self._year_json_path(year)
        if not path.exists():
            return False
        try:
            previous = load_json(path)
        except (OSError, ValueError):
            return False
        if not isinstance(previous, dict) or len(previous.get("sessions", [])) <= 1:
            return False

        # A year whose programme covered only one track of a merged conference
        # was saved with the other track's papers removed outright, so it has no
        # Unassigned bucket. Re-parsing brings those papers back from the raw
        # records; drop them again rather than bucketing what was deliberately
        # excluded. Years that do carry a bucket keep using it.
        drop_unknown = not any(
            session.get("session_name") == "Unassigned"
            for session in previous["sessions"]
        )
        # Papers the saved layout cannot know about because they did not exist
        # when it was made. Never dropped: they are the point of a refresh.
        keep_articles = keep_articles or set()

        layout: Dict[str, Tuple[int, str, str]] = {}
        for session in previous["sessions"]:
            if session.get("session_name") == "Unassigned":
                continue
            for paper in session.get("papers", []):
                key = str(paper.get("article_number") or "")
                if key:
                    layout[key] = (
                        session.get("session_number") or 0,
                        session.get("session_code") or "",
                        session.get("session_name") or "",
                    )
        if not layout:
            return False

        papers = [p for s in year_data.get("sessions", []) for p in s.get("papers", [])]
        grouped: Dict[Tuple[int, str, str], List[Dict[str, Any]]] = {}
        dropped = 0
        for paper in papers:
            article = str(paper.get("article_number") or "")
            entry = layout.get(article)
            if entry is None:
                if drop_unknown and article not in keep_articles:
                    dropped += 1
                    continue
                entry = (10 ** 6, "", "Unassigned")
            grouped.setdefault(entry, []).append(paper)
        if dropped:
            logger.info(
                "[%s] %d papers absent from the saved programme dropped again", year, dropped
            )

        ordered: List[Dict[str, Any]] = []
        for position, key in enumerate(sorted(grouped), start=1):
            _, code, name = key
            session = {
                "session_number": position,
                "session_code": code,
                "session_name": name,
                "papers": grouped[key],
            }
            for index, paper in enumerate(session["papers"], start=1):
                number = f"{position}.{index}"
                paper["session_number"] = position
                paper["session_name"] = name
                paper["paper_number"] = number
                paper["inferred_paper_number"] = number
            ordered.append(session)

        year_data["sessions"] = ordered
        return True

    def reparse_year(self, year: int, keep_articles: Optional[Set[str]] = None) -> bool:
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
        self._restore_session_layout(year, year_data, keep_articles=keep_articles)
        self._apply_track_filter(year, year_data)
        self._apply_session_overrides(year, year_data)
        self._restore_full_abstracts(year_data)  # [c]
        # A journal year rebuilt from cached records carries its Early Access
        # pseudo-issue again, so strip it here - the one place that writes a
        # year file - rather than in each caller.
        if self.config.is_journal:
            early = self._extract_early_access_from_year_data(year, year_data)
            self._save_early_access(early, scraped_years={year})
        save_json(self._year_json_path(year), year_data)
        # Raw records carry no affiliations, so the rebuild just dropped every
        # one this year had. reparse_all restores them at the end of its run;
        # a single-year re-parse has to do it for itself, or they silently
        # vanish until somebody re-runs the enrichment.
        self.enrich_affiliations(start_year=year, end_year=year, cache_only=True)
        logger.info(
            "[%s] Re-parsed from cache: %d sessions, %d papers",
            year, len(year_model.sessions),
            sum(len(sess.papers) for sess in year_model.sessions),
        )
        return True

    def cached_article_numbers(self, year: int) -> Set[str]:
        """Article numbers in this year's raw record cache, or an empty set."""

        path = self._records_cache_path(year)
        if not path.exists():
            return set()
        try:
            records = load_json(path)
        except (OSError, ValueError):
            return set()
        found: Set[str] = set()
        for record in records or []:
            if isinstance(record, dict):
                number = str(record.get("articleNumber") or "").strip()
                if number:
                    found.add(number)
        return found

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
        for year in years:
            if self.reparse_year(year):
                rebuilt += 1

        # reparse_year() has already moved each year's Early Access papers into
        # the shared collection; all that is left is dropping the ones that
        # have since been given a real issue.
        if self.config.is_journal and years:
            self._prune_published_early_access()

        # Raw records carry no affiliations, so a reparse drops every one we
        # had. Re-apply from cache - no network, and without this they vanish
        # until somebody remembers to re-run the enrichment.
        restored = self.enrich_affiliations(cache_only=True)
        if restored:
            logger.info("%s: restored affiliations for %d papers from cache.",
                        self.config.conference_name, restored)

        logger.info("%s: re-parsed %d cached years.", self.config.conference_name, rebuilt)
        return rebuilt

    @staticmethod
    def _paper_keys(paper: Dict[str, Any]) -> List[str]:
        """Identity keys for matching a paper across Early Access and issues."""

        keys: List[str] = []
        article_number = str(paper.get("article_number") or "").strip()
        if article_number:
            keys.append(f"id:{article_number}")
        doi = str(paper.get("doi") or "").strip().lower()
        if doi:
            keys.append(f"doi:{doi}")
        title = re.sub(r"\W+", " ", str(paper.get("title") or "").lower()).strip()
        if title:
            keys.append(f"t:{title}")
        return keys

    def _prune_published_early_access(self) -> int:
        """
        Drop Early Access entries that now appear in a real issue.

        IEEE moves a paper out of Early Access once it is assigned to an issue.
        Without this, an incremental update keeps the stale Early Access copy
        forever and the paper shows up twice - once under Early Access and once
        under its published issue.

        Returns the number of entries removed.
        """

        path = self._early_access_json_path()
        if not path.exists():
            return 0
        try:
            payload = load_json(path)
        except (OSError, ValueError) as exc:
            logger.warning("Early Access file unreadable, skipping prune: %s", exc)
            return 0

        papers = payload.get("papers") or []
        if not papers:
            return 0

        # Every paper that now lives in a normal year file.
        published: set[str] = set()
        for year_path in self.config.json_dir.glob("*.json"):
            if not year_path.stem.isdigit():
                continue
            try:
                year_data = load_json(year_path)
            except (OSError, ValueError):
                continue
            for session in year_data.get("sessions", []):
                if self._is_early_issue_session(session.get("session_name", "")):
                    continue
                for paper in session.get("papers", []):
                    published.update(self._paper_keys(paper))

        if not published:
            return 0

        kept = [p for p in papers if not any(k in published for k in self._paper_keys(p))]
        removed = len(papers) - len(kept)
        if removed:
            payload["papers"] = kept
            save_json(path, payload)
            logger.info(
                "Early Access: dropped %d entr%s now published in a real issue (%d remain).",
                removed, "y" if removed == 1 else "ies", len(kept),
            )
        return removed

    # ------------------------------------------------------------------
    # Session structure from the printed programme
    # ------------------------------------------------------------------

    def _toc_pdf_path(self, year: int) -> Path:
        return self.config.cache_dir / "toc" / f"{year}.pdf"

    @staticmethod
    def _lacks_sessions(year_data: Dict[str, Any]) -> bool:
        """True when a year has no real session structure worth keeping."""

        # One session holding an entire year is collapsed, whatever it is
        # called - ISSCC 2006 came back as a single session named "SRAM"
        # containing all 304 papers, which a name check would have missed.
        return len(year_data.get("sessions", [])) <= 1

    def enrich_sessions_from_toc(self, year: int, only_if_missing: bool = True) -> bool:
        """
        Rebuild a year's sessions from the proceedings Table of Contents.

        The search API only exposes session headers for ISSCC, but RFIC, CICC
        and VLSI all publish the programme as a front-matter PDF, which is
        fetchable and lists every session. Applied only when it maps a good
        share of the year's papers - otherwise the year keeps what it had.
        """

        import toc_sessions as toc

        # A journal has issues, not sessions. SSCL from 2020 is one volume
        # group a year, which _lacks_sessions would otherwise read as a
        # collapsed conference and hand to the programme pass.  # [c]
        if self.config.is_journal:
            return False

        records_path = self._records_cache_path(year)
        year_path = self._year_json_path(year)
        if not records_path.exists() or not year_path.exists():
            return False

        try:
            records = load_json(records_path)
            year_data = load_json(year_path)
        except (OSError, ValueError):
            return False

        if only_if_missing and not self._lacks_sessions(year_data):
            logger.debug(
                "[%s %s] already has sessions; leaving it alone",
                self.config.conference_id, year,
            )
            return False

        # 1. Preferred: IEEE's own session headings from the TOC endpoint.
        #    This is what Xplore renders as session bars on the proceedings
        #    page. CICC populates it; RFIC and VLSI do not.
        primary = records[0] if records else {}
        publication = primary.get("publicationNumber")
        issue = primary.get("isNumber")
        if publication and issue:
            try:
                topics = toc.fetch_major_topics(str(publication), str(issue))
            except HttpError as exc:
                logger.warning("[%s %s] TOC endpoint failed: %s", self.config.conference_id, year, exc)
                topics = {}
            if topics:
                applied, detail = toc.sessions_from_major_topics(year_data, topics)
                if applied:
                    self._apply_track_filter(year, year_data)
                    self._apply_session_overrides(year, year_data)
                    save_json(year_path, year_data)
                    logger.info("[%s %s] sessions from %s", self.config.conference_id, year, detail)
                    return True
                logger.info("[%s %s] headings not applied: %s", self.config.conference_id, year, detail)

        # 2. Fallback: parse the printed programme PDF. Try each candidate -
        #    RFIC ships a 2-page "Session List" with no structure alongside a
        #    32-page "Table of Contents" that has all of it.
        applied = False
        detail = "no programme document"
        tried = 0
        parsed = []
        for candidate in toc.find_toc_records(records):
            tried += 1
            article = candidate.get("articleNumber")
            try:
                pdf_bytes = toc.download_toc(
                    candidate, self._toc_pdf_path(year).with_name(f"{year}-{article}.pdf")
                )
            except HttpError as exc:
                logger.warning("[%s %s] programme download failed: %s", self.config.conference_id, year, exc)
                continue
            if not pdf_bytes:
                detail = f"programme PDF unavailable ({tried} candidate(s) tried)"
                continue

            raw_text = toc.extract_text(pdf_bytes)
            programme = toc.parse_programme(raw_text)
            if not programme.session_names:
                detail = f"{candidate.get('articleTitle')!r} has no recognisable sessions"
                continue
            parsed.append((programme, raw_text, candidate))

        # The conference's own website, for years IEEE indexes no programme for.
        # It competes with the Xplore candidates on the same terms.
        web_url = toc.web_programme_url(self.config.conference_id, year)
        if web_url:
            raw_text = toc.web_programme_text(
                web_url, self._toc_pdf_path(year).parent, year
            )
            if raw_text:
                programme = toc.parse_programme(raw_text)
                if programme.session_names:
                    parsed.append((programme, raw_text, {"articleTitle": f"web: {web_url}"}))

        # For VLSI 2022+ the two tracks share one publication, so papers
        # missing from the Circuits programme are Technology papers and
        # are dropped rather than bucketed as unassigned.
        merged_tracks = bool(self.config.circuits_only) and "technology and circuits" in (
            (records[0].get("publicationTitle") or "").lower() if records else ""
        )

        def grouping_score(data: Dict[str, Any]) -> Tuple[int, int]:
            """Papers actually placed, then how many named sessions hold them."""

            sessions = data.get("sessions", [])
            total = sum(len(session.get("papers", [])) for session in sessions)
            real = [
                session for session in sessions
                if session.get("session_name") not in ("Unassigned", "General")
            ]
            # Ignore any session that holds more than 40% of the year: that is
            # a bucket, not a session, and counting its papers as "placed"
            # makes a broken grouping look like the best one available.
            credible = [
                session for session in real
                if not total or len(session.get("papers", [])) <= 0.4 * total
            ]
            placed = sum(len(session["papers"]) for session in credible)
            return placed, len(credible)

        # What the year already has. A programme is only worth applying if it
        # beats this: ISSCC derives its sessions from the records themselves,
        # and re-deriving 2002 from the printed programme turned 26 sessions
        # into 16. Re-running a healthy year must never cost it structure.
        incumbent = grouping_score(year_data)

        # A year often ships several front-matter documents - a two-page
        # "Session List" beside a thirty-page "Table of Contents". Score them
        # by the grouping they actually produce rather than by how much text
        # they parse: a document with more session headings can still match
        # fewer papers, and picking it by size alone regressed RFIC 2008 and
        # 2014. Each trial runs on its own copy, so a losing candidate cannot
        # leave a partial grouping behind.
        best = None
        for programme, raw_text, candidate in parsed:
            trial = copy.deepcopy(year_data)
            applied, trial_detail = toc.assign_sessions(
                trial, programme, raw_text=raw_text, drop_unmatched=merged_tracks
            )
            if not applied:
                detail = trial_detail
                continue
            sessions = trial.get("sessions", [])
            assigned = sum(
                len(session["papers"])
                for session in sessions
                if session.get("session_name") != "Unassigned"
            )
            named = sum(1 for s in sessions if s.get("session_name") != "Unassigned")
            score = (assigned, named)
            if best is None or score > best[0]:
                best = (score, trial, trial_detail, candidate)

        if best is not None and best[0] <= incumbent:
            logger.info(
                "[%s %s] keeping the existing grouping: programme scores %s, current %s",
                self.config.conference_id, year, best[0], incumbent,
            )
            best = None
            detail = "existing grouping is better; left as-is"

        if best is not None:
            _, chosen, detail, candidate = best
            year_data["sessions"] = chosen["sessions"]
            applied = True
            detail = f"{detail} (from {candidate.get('articleTitle')!r})"

        if not applied:
            logger.info("[%s %s] programme not applied: %s", self.config.conference_id, year, detail)
            return False

        self._apply_track_filter(year, year_data)
        self._apply_session_overrides(year, year_data)
        save_json(year_path, year_data)
        logger.info(
            "[%s %s] sessions from programme: %s",
            self.config.conference_id, year, detail,
        )
        return True

    def _apply_session_overrides(self, year: int, year_data: Dict[str, Any]) -> None:
        """Tidy the session structure once it is final."""

        import session_overrides
        import toc_sessions as toc

        # A grouping where one session holds most of the year is not structure,
        # it is noise wearing a session's name. CICC files its session-overview
        # records in a block at the END of the search results rather than
        # interleaved with the papers, so position-based grouping put 104 of
        # 2015's 123 papers under "Low power analog" and 107 of 2018's 109
        # under one heading. A single honest "General" session is better than a
        # page that claims a structure the data does not support; overrides
        # still run afterwards and can place papers properly.
        if not self.config.is_journal:
            sessions = year_data.get("sessions", [])
            real = [
                session for session in sessions
                if session.get("session_name") not in ("Unassigned", "General")
            ]
            total = sum(len(session.get("papers", [])) for session in sessions)
            if real and total >= 20:
                biggest = max(len(session.get("papers", [])) for session in real)
                if biggest > 0.6 * total:
                    logger.info(
                        "[%s %s] one session holds %d of %d papers; keeping a single"
                        " General session instead",
                        self.config.conference_id, year, biggest, total,
                    )
                    papers = [p for s in sessions for p in s.get("papers", [])]
                    for index, paper in enumerate(papers, start=1):
                        paper["session_number"] = 1
                        paper["session_name"] = "General"
                        paper["paper_number"] = f"1.{index}"
                        paper["inferred_paper_number"] = f"1.{index}"
                    year_data["sessions"] = [{
                        "session_number": 1,
                        "session_code": "1",
                        "session_name": "General",
                        "papers": papers,
                    }]

        # The chairs' session-introduction records look like papers and inflate
        # the session they sit in; remove them before the overrides run, so an
        # override never has to name one.
        removed = toc.drop_session_overview_records(year_data)
        if removed:
            logger.info(
                "[%s %s] %d session-overview record(s) removed",
                self.config.conference_id, year, removed,
            )
        session_overrides.apply_overrides(self.config.conference_id, year, year_data)

    def _apply_track_filter(self, year: int, year_data: Dict[str, Any]) -> None:
        """Drop the devices half of a merged conference, where we know it."""

        if self.config.conference_id == "esscirc":
            import esserc_tracks

            sessions, papers = esserc_tracks.drop_device_content(year, year_data)
            if sessions or papers:
                logger.info(
                    "[esscirc %s] dropped %d device session(s) and %d device paper(s)",
                    year, sessions, papers,
                )
        elif self.config.conference_id == "vlsi":
            import vlsi_tracks

            sessions, papers = vlsi_tracks.drop_technology_papers(year, year_data)
            if sessions or papers:
                logger.info(
                    "[vlsi %s] dropped %d Technology paper(s), %d empty session(s)",
                    year, papers, sessions,
                )

    def enrich_sessions_all(
        self,
        start_year: Optional[int] = None,
        end_year: Optional[int] = None,
        only_if_missing: bool = True,
    ) -> int:
        """Apply the programme to every cached year. Returns years improved."""

        cache_dir = self.config.cache_dir / "records"
        if not cache_dir.is_dir():
            return 0
        years = sorted(
            (int(p.stem) for p in cache_dir.glob("*.json") if p.stem.isdigit()),
            reverse=True,
        )
        improved = 0
        for year in years:
            if start_year is not None and year < start_year:
                continue
            if end_year is not None and year > end_year:
                continue
            if self.enrich_sessions_from_toc(year, only_if_missing=only_if_missing):
                improved += 1
        logger.info(
            "%s: programme applied to %d of %d years.",
            self.config.conference_name, improved, len(years),
        )
        return improved

    # ------------------------------------------------------------------
    # Author affiliations (one extra request per paper)
    # ------------------------------------------------------------------

    def _full_abstract_cache_path(self) -> Path:  # [c]
        return self.config.cache_dir / "abstracts_full.json"

    def _restore_full_abstracts(self, year_data: Dict[str, Any]) -> int:  # [c]
        """
        Put back the full abstracts tools/restore_abstracts.py fetched.

        The search API cuts abstracts at about 400 characters (91% of stored
        abstracts, measured 2026-10-27) and every scrape or re-parse rebuilds a
        year from those records, so the full text is re-applied before the write.
        """

        cache = getattr(self, "_full_abstracts", None)
        if cache is None:
            path = self._full_abstract_cache_path()
            try:
                cache = load_json(path) if path.exists() else {}
            except (OSError, ValueError):
                cache = {}
            self._full_abstracts = cache
        restored = 0
        for session in year_data.get("sessions", []):
            for paper in session.get("papers", []):
                full = cache.get(str(paper.get("article_number") or ""))
                if full and len(full) > len(paper.get("abstract") or ""):
                    paper["abstract"] = full
                    restored += 1
        return restored

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
        cache_only: bool = False,
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

            # Collect what this year still needs, then fetch in parallel.
            pending: List[Dict[str, Any]] = []
            for session in year_data.get("sessions", []):
                for paper in session.get("papers", []):
                    if paper.get("affiliations"):
                        continue
                    if not paper.get("article_number"):
                        continue
                    pending.append(paper)

            if max_papers is not None:
                pending = pending[: max(0, max_papers - updated)]

            to_fetch = [] if cache_only else [
                p["article_number"] for p in pending
                if p["article_number"] not in cache
            ]
            to_fetch = list(dict.fromkeys(to_fetch))  # de-duplicate, keep order

            if to_fetch:
                workers = max(1, int(self.config.affiliation_workers))

                def _lookup(article_number: str):
                    try:
                        return article_number, self._fetch_author_affiliations(article_number)
                    except HttpError as exc:
                        logger.warning(
                            "[%s] affiliation fetch failed for %s: %s",
                            year, article_number, exc,
                        )
                        return article_number, None

                with ThreadPoolExecutor(max_workers=workers) as pool:
                    for article_number, affiliations in pool.map(_lookup, to_fetch):
                        if affiliations is None:
                            continue
                        cache[article_number] = affiliations
                        fetched_since_save += 1
                        if fetched_since_save >= 50:
                            save_json(cache_path, cache)
                            fetched_since_save = 0

            for paper in pending:
                affiliations = cache.get(paper["article_number"])
                if not affiliations:
                    continue
                paper["affiliations"] = affiliations
                paper["author_affiliations_raw"] = "; ".join(
                    dict.fromkeys(a for a in affiliations if a)
                )
                updated += 1
                year_changed = True

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

        if self.config.is_journal:
            # scrape_year has already moved each year's Early Access papers
            # into the shared collection; all that is left is dropping the ones
            # IEEE has since given a real issue.
            self._prune_published_early_access()

        if failed_years:
            logger.warning(
                "%s: %d year(s) could not be fetched and were left unchanged: %s",
                self.config.conference_name, len(failed_years), failed_years,
            )


__all__ = ["Scraper"]
