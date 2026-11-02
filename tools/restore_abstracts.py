# [c] whole file
"""
Restore full abstracts, newest papers first. (Claude, 2026-10-27)

IEEE Xplore's search API - the source of every record here - cuts abstracts at
about 400 characters: 56,255 of 61,585 stored abstracts were 395-410 long on
2026-10-27. The full text needs one request per paper to
/rest/document/<articleNumber>/abstract; 3 workers like the affiliation
backfill, about 2 a second, so several hours for the corpus. Built like backfill_affiliations.py, so it can be stopped and resumed:

* Every fetched abstract is cached in `cache/<source>/abstracts_full.json`
  (article number -> text), flushed every 50 papers; a kill loses at most 50.
* Scraper._restore_full_abstracts() re-applies the cache before every year
  file is written, so a refresh or re-parse keeps the full text.
* Work runs by year, newest first, across all sources.
* It refuses to start while it or an affiliation backfill is already running:
  two processes double the request rate at IEEE.

    python tools/restore_abstracts.py                  # everything
    python tools/restore_abstracts.py --from-year 2020 # recent only
    python tools/restore_abstracts.py --budget 500     # stop after N papers

Progress is written to `cache/abstract_progress.json`.

Pacing (2026-11-01): the first run was blocked (HTTP 418) after about 8.5 hours
and 46k papers, then kept retrying for five days with nothing restored. Now:

* Scheduled rest: after a random 55-65 min of fetching (--work-minutes 60) it
  pauses a random 15-45 min. Only long jobs ever reach the limit.
* Slow and safe by default, since it is a one-off job: 1 worker, a random
  1-5 s gap between requests (new seed every hour of run time), one try per request so every refusal is seen. A
  second run through Yi's Mac at the old 3 workers (about 2/s) drew 418s from
  the first minute, which retries hid, and was blocked within the hour.
* First signs: any single refusal (418/429/403, or no connection) doubles the
  interval (up to 16 s) and pauses --soft-minutes (default 5). 300 clean
  requests halve the interval back.
* Block guard: 3 refusals in a row stop all workers at once.
  It waits --rest-minutes, tests one paper, and resumes if that works. Each
  further failure doubles the wait (30, 60, 120, 120 min). After
  --max-pauses failed tests (default 4) it saves and exits with code 3; re-run
  it later to resume.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import CONFERENCES, get_config  # noqa: E402
from textclean import clean_text  # noqa: E402
import requests  # noqa: E402
from utils import LONG_RUN_REST_SECONDS, LONG_RUN_WORK_SECONDS, HttpError, get_session, load_json, save_json, setup_logging  # noqa: E402

logger = logging.getLogger("abstracts")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROGRESS_PATH = PROJECT_ROOT / "cache" / "abstract_progress.json"
LOCK_PATH = PROJECT_ROOT / "cache" / "abstract_restore.lock"
OTHER_LOCKS = [PROJECT_ROOT / "cache" / "affiliation_backfill.lock"]
TRUNCATED = range(395, 411)     # lengths the search API's cut produces
BATCH = 60                      # papers between block checks and progress saves
BLOCK_CODES = ("418", "429", "403")
BLOCK_STREAK = 3                # refusals in a row that mean "we are blocked"
MAX_REST_MINUTES = 120
GAP_MIN, GAP_MAX = 1.0, 5.0     # random gap between requests, s (no fixed pattern)
MAX_INTERVAL = 16.0             # backoff multiplier ceiling: gaps up to 8x after pushback
CLEAN_TO_SPEED_UP = 300         # clean requests before the interval halves back
REFUSED = "refused"             # HttpError text marker for a refusal (block code or no connection)


class Blocked(Exception):
    """IEEE kept refusing after every allowed pause."""


class Pacer:
    """Scheduled rests on long runs; stop, wait and test when IEEE blocks."""

    def __init__(self, work_minutes: float, rest_minutes: float, max_pauses: int,
                 interval: float = 2.0, soft_minutes: float = 5.0):
        self.work_s, self.rest_s, self.max_pauses = work_minutes * 60, rest_minutes * 60, max_pauses
        self.base = self.interval = interval
        self.soft_s = soft_minutes * 60
        self.lock = threading.Lock()
        self.streak = 0
        self.clean = 0
        self.next_at = 0.0
        self.rng, self.seeded_at = random.Random(os.urandom(16)), time.monotonic()
        self.blocked = threading.Event()
        self.work_started = time.monotonic()

    def wait_slot(self) -> None:
        """Random gap of 1-5 s (scaled up after pushback); new seed every hour of run time."""
        with self.lock:
            now = time.monotonic()
            if now - self.seeded_at > 3600:
                self.rng, self.seeded_at = random.Random(os.urandom(16)), now
            gap = self.rng.uniform(GAP_MIN, GAP_MAX) * (self.interval / self.base)
            start = max(now, self.next_at)
            self.next_at = start + gap
        if start > now:
            time.sleep(start - now)

    def note(self, exc: Exception | None) -> None:
        """Every refusal counts, even one a later try gets past: slow down at the first sign."""
        soft = False
        with self.lock:
            if exc is None:
                self.streak = 0
                self.clean += 1
                if self.clean >= CLEAN_TO_SPEED_UP and self.interval > self.base:
                    self.interval = max(self.base, self.interval / 2)
                    self.clean = 0
                    logger.info("%d clean requests: interval back to %.1f s.", CLEAN_TO_SPEED_UP, self.interval)
                return
            if REFUSED not in str(exc):
                return                          # a plain error (404, bad JSON): not a sign of blocking
            self.streak += 1
            self.clean = 0
            self.interval = min(MAX_INTERVAL, self.interval * 2)
            if self.streak >= BLOCK_STREAK:
                self.blocked.set()
            else:
                soft = True
            logger.warning("Refused (%d in a row): interval now %.1f s.", self.streak, self.interval)
        if soft:
            self._sleep(self.soft_s, "First signs of pushback")

    def _sleep(self, seconds: float, why: str) -> None:
        until = dt.datetime.now() + dt.timedelta(seconds=seconds)
        logger.warning("%s: pausing %.0f min, until %s.", why, seconds / 60, until.strftime("%H:%M"))
        time.sleep(seconds)
        self.work_started = time.monotonic()

    def maybe_rest(self) -> None:
        if not hasattr(self, "work_len"):
            self.work_len = self.rng.uniform(*LONG_RUN_WORK_SECONDS) * self.work_s / 3600
        if self.work_s > 0 and time.monotonic() - self.work_started >= self.work_len:
            self.work_len = self.rng.uniform(*LONG_RUN_WORK_SECONDS) * self.work_s / 3600
            self._sleep(self.rng.uniform(*LONG_RUN_REST_SECONDS),
                        "Scheduled rest after %.0f min of fetching (random length)" % (self.work_s / 60))

    def recover(self, probe) -> None:
        """Called while blocked: wait, test one request, repeat; raise Blocked when out of pauses."""
        rest = self.rest_s
        for attempt in range(1, self.max_pauses + 1):
            self._sleep(rest, "IEEE is blocking (%d refusals in a row), pause %d of %d"
                        % (self.streak, attempt, self.max_pauses))
            if probe():
                logger.info("Test request worked; resuming.")
                with self.lock:
                    self.streak = 0
                    self.blocked.clear()
                return
            rest = min(rest * 2, MAX_REST_MINUTES * 60)
        raise Blocked()


def _process_alive(pid: int) -> bool:
    try:
        import subprocess
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                             capture_output=True, text=True, timeout=15).stdout
        return str(pid) in out
    except Exception:
        return False


def _lock_holder(path: Path) -> int:
    try:
        pid = int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return 0
    return pid if pid != os.getpid() and _process_alive(pid) else 0


def acquire_lock() -> bool:
    for path in [LOCK_PATH] + OTHER_LOCKS:
        pid = _lock_holder(path) if path.exists() else 0
        if pid:
            logger.error("%s is held by running PID %s; stop it first (two IEEE clients "
                         "double the request rate and get us blocked).", path.name, pid)
            return False
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCK_PATH.write_text(str(os.getpid()), encoding="utf-8")
    return True


def release_lock() -> None:
    try:
        if LOCK_PATH.exists() and LOCK_PATH.read_text(encoding="utf-8").strip() == str(os.getpid()):
            LOCK_PATH.unlink()
    except OSError:
        pass


def _papers(data):
    """Papers of a year file or of early_access.json."""
    if "papers" in data:
        return data["papers"]
    return [p for s in data.get("sessions", []) for p in s.get("papers", [])]


def _files(config):
    json_dir = config.json_dir
    years = sorted((p for p in json_dir.glob("*.json") if p.stem.isdigit()), key=lambda p: -int(p.stem))
    early = json_dir / "early_access.json"
    return ([early] if early.exists() else []) + years


def _apply(path: Path, cache: dict) -> int:
    data = load_json(path)
    changed = 0
    for paper in _papers(data):
        full = cache.get(str(paper.get("article_number") or ""))
        if full and len(full) > len(paper.get("abstract") or ""):
            paper["abstract"] = full
            changed += 1
    if changed:
        save_json(path, data)
    return changed


def main() -> int:
    setup_logging()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--from-year", type=int, default=1990)
    parser.add_argument("--budget", type=int, default=0, help="Stop after about N papers (0 = no limit).")
    parser.add_argument("--sources", default="", help="Comma-separated source ids (default: all).")
    parser.add_argument("--work-minutes", type=float, default=60, help="Fetch about this long (+-8%%, random), then rest a random 15-45 min (0 = never).")
    parser.add_argument("--rest-minutes", type=float, default=30, help="First pause when blocked (doubles each failed test).")
    parser.add_argument("--max-pauses", type=int, default=4, help="Failed tests while blocked before giving up.")
    parser.add_argument("--interval", type=float, default=2.0, help="Backoff base: gaps are random 1-5 s x (current/base) after pushback.")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--soft-minutes", type=float, default=5, help="Pause after a single refusal.")
    args = parser.parse_args()
    pacer = Pacer(args.work_minutes, args.rest_minutes, args.max_pauses,
                  interval=args.interval, soft_minutes=args.soft_minutes)
    if not acquire_lock():
        return 1

    sources = [s.strip() for s in args.sources.split(",") if s.strip()] or list(CONFERENCES)
    configs = {cid: get_config(cid) for cid in sources}
    caches = {cid: load_json(configs[cid].cache_dir / "abstracts_full.json")
              if (configs[cid].cache_dir / "abstracts_full.json").exists() else {} for cid in sources}

    # Survey: (year, source, file) -> article numbers still truncated.
    work = []
    for cid in sources:
        for path in _files(configs[cid]):
            year = 9999 if not path.stem.isdigit() else int(path.stem)
            if year < args.from_year:
                continue
            todo = [str(p["article_number"]) for p in _papers(load_json(path))
                    if p.get("article_number") and len(p.get("abstract") or "") in TRUNCATED
                    and str(p["article_number"]) not in caches[cid]]
            if todo:
                work.append((year, cid, path, todo))
    work.sort(key=lambda w: -w[0])
    total = sum(len(w[3]) for w in work)
    logger.info("Abstract restore: %d papers in %d files, roughly %.1f hours. Safe to stop and resume.",
                total, len(work), total * (GAP_MIN + GAP_MAX) / 2 / 3600)

    started, done = dt.datetime.now(), 0
    try:
        for year, cid, path, todo in work:
            cache, cache_path = caches[cid], configs[cid].cache_dir / "abstracts_full.json"
            base = configs[cid].base_url
            if args.budget:
                todo = todo[: max(0, args.budget - done)]
                if not todo:
                    logger.info("Budget of %d reached.", args.budget)
                    return 0

            def lookup(article):
                if pacer.blocked.is_set():      # blocked: don't spend requests until the test passes
                    return article, None
                try:
                    data = fetch_once(f"{base}/rest/document/{article}/abstract", pacer,
                                      configs[cid].request_timeout_seconds)
                    pacer.note(None)
                    return article, clean_text(" ".join(str(data.get("abstract") or "").split()))
                except HttpError as exc:
                    pacer.note(exc)
                    logger.warning("[%s %s] %s: %s", cid, path.stem, article, exc)
                    return article, None

            # One-off job, so slow and safe: 1 worker, 2 s apart (2026-11-01; 3 workers
            # at ~2/s drew 418s from the first minute and a block within the hour).
            # Batches, so a block is noticed within one batch and its papers retried.
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                queue = list(todo)
                while queue:
                    batch, queue = queue[:BATCH], queue[BATCH:]
                    failed = []
                    for article, text in pool.map(lookup, batch):   # in order
                        if text is None:
                            failed.append(article)
                            continue
                        if text:
                            cache[article] = text
                        done += 1
                    save_json(cache_path, cache)
                    _progress(started, done, total, year, cid)
                    if pacer.blocked.is_set():
                        pacer.recover(lambda: lookup_probe(base, failed[0], configs[cid]))
                        queue = failed + queue      # retry what the block refused
                    else:
                        pacer.maybe_rest()
            save_json(cache_path, cache)
            applied = _apply(path, cache)
            logger.info("[%s %s] %d abstracts restored (%d/%d done overall)", cid, path.stem, applied, done, total)
            _progress(started, done, total, year, cid)
    except KeyboardInterrupt:
        logger.info("Interrupted; progress is cached.")
        return 130
    except Blocked:
        logger.error("IEEE still blocking after %d pauses; stopped with %d/%d done. "
                     "Re-run later to resume.", args.max_pauses, done, total)
        return 3
    finally:
        for cid in sources:
            save_json(configs[cid].cache_dir / "abstracts_full.json", caches[cid])
    logger.info("Done: %d papers in %s.", done, str(dt.datetime.now() - started).split(".")[0])
    return 0


def fetch_once(url: str, pacer: Pacer, timeout: float) -> dict:
    """One try, no hidden retries, so the pacer sees every refusal."""
    pacer.wait_slot()
    try:
        resp = get_session().get(url, timeout=timeout)
    except requests.RequestException as exc:     # includes a dropped SSH tunnel
        raise HttpError(f"{REFUSED}: no connection ({exc.__class__.__name__})") from exc
    if resp.status_code in (418, 429, 403, 502, 503, 504):   # 502 on every page = blocked too (2026-11-01)
        raise HttpError(f"{REFUSED}: HTTP {resp.status_code}")
    try:
        resp.raise_for_status()
        return resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise HttpError(f"HTTP {resp.status_code}: {exc}") from exc


def lookup_probe(base, article, config) -> bool:
    """One test request while blocked: a single try, no retries."""
    try:
        resp = get_session().get(f"{base}/rest/document/{article}/abstract",
                                 timeout=config.request_timeout_seconds)
    except requests.RequestException as exc:
        logger.warning("Test request failed: %s", exc)
        return False
    logger.info("Test request: HTTP %s", resp.status_code)
    return resp.status_code == 200


def _progress(started, done, total, year, source):
    save_json(PROGRESS_PATH, {
        "updated": dt.datetime.now().isoformat(timespec="seconds"),
        "started": started.isoformat(timespec="seconds"),
        "papers_done": done, "papers_total": total,
        "percent": round(100.0 * done / total, 1) if total else 100.0,
        "last_year": year, "last_source": source,
    })


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    finally:
        release_lock()
