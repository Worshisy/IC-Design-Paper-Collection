from __future__ import annotations

import json
import logging
import random
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import requests
from tenacity import RetryError, retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from config import get_config


def setup_logging() -> None:
    """Configure root logging with a sensible default format."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )


def ensure_dir(path: Path) -> None:
    """Ensure a directory exists, including parents."""

    path.mkdir(parents=True, exist_ok=True)


def save_text(path: Path, content: str) -> None:
    """Persist a text file using UTF-8 encoding."""

    ensure_dir(path.parent)
    path.write_text(content, encoding="utf-8")


def save_json(path: Path, data: Any) -> None:
    """Persist JSON to disk with UTF-8 encoding and indentation."""

    ensure_dir(path.parent)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def load_json(path: Path) -> Any:
    """Load JSON from disk."""

    return json.loads(path.read_text(encoding="utf-8"))


class RateLimiter:
    """
    Global pacer shared by every IEEE request, whatever the endpoint.

    Two jobs beyond a plain sleep:

    * Adaptive floor - a 5xx/429 doubles the minimum gap between requests (up
      to a ceiling) and a run of clean responses decays it back. A slow patch
      therefore slows the whole scrape instead of being retried through.
    * Circuit breaker - after a number of consecutive failures it stops and
      waits out a long cooldown, which is the polite response to an endpoint
      that is refusing us and avoids looking like a hostile client.

    One shared instance, so the search and authors endpoints cannot each spend
    a "full" budget and together double the real request rate.
    """

    def __init__(
        self,
        *,
        jitter: float = 0.3,
        ceiling: float = 45.0,
        recovery_successes: int = 12,
        break_after: int = 6,
        cooldown: float = 300.0,
        max_cooldowns: int = 3,
        escalation_cooldown: float = 8.0,
        reset_after_quiet: float = 90.0,
    ) -> None:
        self._lock = threading.Lock()
        self._last_request = 0.0
        self._floor = 0.0
        self._consecutive_failures = 0
        self._successes_since_penalty = 0
        self._cooldowns_taken = 0
        self.jitter = jitter
        self.ceiling = ceiling
        self.recovery_successes = recovery_successes
        self.break_after = break_after
        self.cooldown = cooldown
        self.max_cooldowns = max_cooldowns
        self.escalation_cooldown = escalation_cooldown
        self.reset_after_quiet = reset_after_quiet
        self._last_escalation = 0.0
        self._last_failure = 0.0
        self._log = logging.getLogger("http.rate")

    def wait(self, min_interval: float) -> None:
        """
        Block until the caller may issue its request.

        The slot is RESERVED inside the lock, before sleeping. Updating the
        timestamp after the sleep instead would let parallel workers all read
        the same stale value, compute the same short delay and fire at once -
        so the configured spacing would not actually be enforced.
        """

        with self._lock:
            interval = max(min_interval, self._floor)
            interval += random.uniform(0.0, self.jitter * interval)
            now = time.monotonic()
            start_at = max(now, self._last_request + interval)
            self._last_request = start_at
            breaker = self._pending_cooldown()
        if breaker:
            self._log.warning(
                "Pausing %.0fs after %d consecutive failures before retrying.",
                breaker, self._consecutive_failures,
            )
            time.sleep(breaker)
        delay = start_at - time.monotonic()
        if delay > 0:
            time.sleep(delay)

    def _pending_cooldown(self) -> float:
        if self._consecutive_failures < self.break_after:
            return 0.0
        if self._cooldowns_taken >= self.max_cooldowns:
            return 0.0
        self._cooldowns_taken += 1
        self._consecutive_failures = 0
        return self.cooldown

    def record_success(self) -> None:
        with self._lock:
            self._consecutive_failures = 0
            self._cooldowns_taken = 0
            if self._floor <= 0:
                return
            # A long clean stretch means whatever upset the endpoint is over.
            if self._last_failure and (time.monotonic() - self._last_failure) > self.reset_after_quiet:
                self._floor = 0.0
                self._successes_since_penalty = 0
                self._log.info("Upstream quiet again: request floor cleared.")
                return
            self._successes_since_penalty += 1
            if self._successes_since_penalty >= self.recovery_successes:
                self._successes_since_penalty = 0
                self._floor = 0.0 if self._floor <= 1.0 else self._floor / 2.0
                self._log.info("Backing off less: request floor now %.1fs", self._floor)

    def record_failure(self) -> None:
        with self._lock:
            now = time.monotonic()
            self._consecutive_failures += 1
            self._successes_since_penalty = 0
            self._last_failure = now

            # Escalate once per wave. Several workers failing on the same
            # upstream hiccup is one event, not N, and doubling N times lands
            # straight on the ceiling and stalls everything.
            if now - self._last_escalation < self.escalation_cooldown:
                return
            self._last_escalation = now

            previous = self._floor
            self._floor = min(self.ceiling, (self._floor * 2.0) if self._floor else 2.0)
            if self._floor != previous:
                self._log.warning(
                    "Upstream pushing back (%d in a row): request floor now %.1fs",
                    self._consecutive_failures, self._floor,
                )


def _build_rate_limiter() -> RateLimiter:
    cfg = get_config(create_dirs=False)
    return RateLimiter(
        jitter=cfg.rate_limit_jitter,
        ceiling=cfg.rate_limit_ceiling_seconds,
        recovery_successes=cfg.rate_limit_recovery_successes,
        break_after=cfg.circuit_break_failures,
        cooldown=cfg.circuit_break_cooldown_seconds,
        max_cooldowns=cfg.circuit_break_max_cooldowns,
        escalation_cooldown=cfg.rate_limit_escalation_cooldown,
        reset_after_quiet=cfg.rate_limit_reset_after_quiet,
    )


RATE_LIMITER = _build_rate_limiter()


class HttpError(RuntimeError):
    """Raised when an HTTP request fails after all retries."""


def _build_session() -> requests.Session:
    """Create a preconfigured Requests session."""

    cfg = get_config(create_dirs=False)
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": cfg.user_agent,
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": "https://ieeexplore.ieee.org",
            "Referer": "https://ieeexplore.ieee.org/xpl/conhome/1000708/all-proceedings",
        }
    )
    return session


_THREAD_LOCAL = threading.local()


def get_session() -> requests.Session:
    """
    Return this thread's HTTP session.

    requests.Session is not safe to share between threads, and the affiliation
    pass fetches in parallel, so each worker gets its own. Connection pooling
    still happens within a thread.
    """

    session = getattr(_THREAD_LOCAL, "session", None)
    if session is None:
        session = _build_session()
        _THREAD_LOCAL.session = session
    return session


def make_retrying_post() -> Callable[[str, Dict[str, Any]], Dict[str, Any]]:
    """
    Build a POST wrapper with tenacity retry logic.

    Returns a callable that accepts (url, json_payload) and returns parsed JSON.
    """

    cfg = get_config(create_dirs=False)
    logger = logging.getLogger("http")

    @retry(
        retry=retry_if_exception_type(requests.RequestException),
        stop=stop_after_attempt(cfg.max_retries),
        wait=wait_exponential(
            multiplier=cfg.backoff_initial_seconds,
            max=cfg.backoff_max_seconds,
        ),
        reraise=True,
    )
    def _post(url: str, payload: Dict[str, Any], min_interval: float) -> Dict[str, Any]:
        session = get_session()
        RATE_LIMITER.wait(min_interval)
        logger.debug("POST %s", url)
        try:
            resp = session.post(url, json=payload, timeout=cfg.request_timeout_seconds)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException:
            RATE_LIMITER.record_failure()
            raise
        RATE_LIMITER.record_success()
        return data

    def wrapper(
        url: str,
        payload: Dict[str, Any],
        min_interval: Optional[float] = None,
    ) -> Dict[str, Any]:
        try:
            return _post(url, payload, cfg.rate_limit_seconds if min_interval is None else min_interval)
        except (RetryError, requests.RequestException, ValueError) as exc:
            raise HttpError(f"Failed to POST {url!r} after retries: {exc}") from exc

    return wrapper


def make_retrying_get() -> Callable[[str], Dict[str, Any]]:
    """
    Build a GET wrapper with the same retry policy as the POST wrapper.

    Used for the per-document authors endpoint, which is a plain GET.
    """

    cfg = get_config(create_dirs=False)
    logger = logging.getLogger("http")

    @retry(
        retry=retry_if_exception_type(requests.RequestException),
        stop=stop_after_attempt(cfg.max_retries),
        wait=wait_exponential(
            multiplier=cfg.backoff_initial_seconds,
            max=cfg.backoff_max_seconds,
        ),
        reraise=True,
    )
    def _get(url: str, min_interval: float) -> Dict[str, Any]:
        session = get_session()
        RATE_LIMITER.wait(min_interval)
        logger.debug("GET %s", url)
        try:
            resp = session.get(url, timeout=cfg.request_timeout_seconds)
            # 418 is what IEEE returns when it decides you are a bot; 429 is
            # the ordinary rate-limit answer. Both mean "slow down", not
            # "retry harder".
            if resp.status_code in (418, 429):
                RATE_LIMITER.record_failure()
                raise requests.HTTPError(f"{resp.status_code} rate limited", response=resp)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException:
            RATE_LIMITER.record_failure()
            raise
        RATE_LIMITER.record_success()
        return data

    def wrapper(url: str, min_interval: Optional[float] = None) -> Dict[str, Any]:
        try:
            return _get(url, cfg.rate_limit_seconds if min_interval is None else min_interval)
        except (RetryError, requests.RequestException, ValueError) as exc:
            raise HttpError(f"Failed to GET {url!r} after retries: {exc}") from exc

    return wrapper


retrying_post = make_retrying_post()
retrying_get = make_retrying_get()
