from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict

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


_SESSION = _build_session()


def get_session() -> requests.Session:
    """Return the shared HTTP session."""

    return _SESSION


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
    def _post(url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        session = get_session()
        logger.debug("POST %s", url)
        resp = session.post(url, json=payload, timeout=cfg.request_timeout_seconds)
        resp.raise_for_status()
        return resp.json()

    def wrapper(url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return _post(url, payload)
        except RetryError as exc:
            raise HttpError(f"Failed to POST {url!r} after retries") from exc

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
    def _get(url: str) -> Dict[str, Any]:
        session = get_session()
        logger.debug("GET %s", url)
        resp = session.get(url, timeout=cfg.request_timeout_seconds)
        resp.raise_for_status()
        return resp.json()

    def wrapper(url: str) -> Dict[str, Any]:
        try:
            return _get(url)
        except RetryError as exc:
            raise HttpError(f"Failed to GET {url!r} after retries") from exc

    return wrapper


retrying_post = make_retrying_post()
retrying_get = make_retrying_get()
