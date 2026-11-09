"""
Serve the generated site locally so paper marks save straight to disk.

Opening site/<id>/index.html directly from disk works too, but a file:// page
cannot write anything - marks then live only in that browser's localStorage
until you press "Export marks". Served over http, every like / mark / note is
POSTed here and written to userdata/annotations.json, which update_database.py
syncs to iCloud.

    python serve.py               # http://localhost:8800
    python serve.py --port 9000
    python serve.py --host 0.0.0.0   # reachable from the LAN, e.g. a phone
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict
from urllib.parse import parse_qs, urlparse  # [c]

from html_builder import annotations_path, write_annotations_seed
from utils import load_json, save_json, setup_logging

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent
SITE_ROOT = PROJECT_ROOT / "site"
MAX_BODY_BYTES = 8 * 1024 * 1024


def _merge_annotations(incoming: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge a browser's annotations into the stored file, newest write winning.

    Per-paper rather than whole-file, so two browsers open at once cannot
    silently drop each other's marks.
    """

    path = annotations_path()
    stored: Dict[str, Any] = {"version": 1, "papers": {}}
    if path.exists():
        try:
            loaded = load_json(path)
            if isinstance(loaded, dict) and isinstance(loaded.get("papers"), dict):
                stored = loaded
        except (OSError, ValueError) as exc:
            logger.warning("Existing annotations unreadable, replacing: %s", exc)

    papers = stored.setdefault("papers", {})
    for paper_id, entry in (incoming.get("papers") or {}).items():
        if not isinstance(entry, dict):
            continue
        current = papers.get(paper_id)
        if not current or str(entry.get("updated", "")) > str(current.get("updated", "")):
            papers[paper_id] = entry

    stored["version"] = 1
    save_json(path, stored)
    return stored


def _review_notes_path() -> Path:
    return annotations_path().parent / "review_notes.json"   # highlights and comments on review pages  # [c]


def _merge_review_notes(page: str, incoming: Dict[str, Any]) -> Dict[str, Any]:
    """Merge one page's notes per note id, newest `updated` winning (removed notes stay as tombstones).  # [c]"""
    path = _review_notes_path()
    stored: Dict[str, Any] = {"version": 1, "pages": {}}
    if path.exists():
        try:
            loaded = load_json(path)
            if isinstance(loaded, dict) and isinstance(loaded.get("pages"), dict):
                stored = loaded
        except (OSError, ValueError) as exc:
            logger.warning("Existing review notes unreadable, replacing: %s", exc)
    notes = stored["pages"].setdefault(page, {})
    for note_id, note in (incoming or {}).items():
        if isinstance(note, dict) and (note_id not in notes or str(note.get("updated", "")) > str(notes[note_id].get("updated", ""))):
            notes[note_id] = note
    save_json(path, stored)
    return notes


class AnnotationHandler(SimpleHTTPRequestHandler):
    """Static file server plus POST endpoints for paper marks and review notes."""

    def _send_json(self, obj: Any) -> None:  # [c]
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - review notes for one page: /api/review-notes?page=<file>  # [c]
        url = urlparse(self.path)
        if url.path.rstrip("/") != "/api/review-notes":
            super().do_GET()
            return
        page = (parse_qs(url.query).get("page") or [""])[0]
        stored = load_json(_review_notes_path()) if _review_notes_path().exists() else {}
        self._send_json({"page": page, "notes": (stored.get("pages") or {}).get(page, {})})

    def do_POST(self) -> None:  # noqa: N802 - http.server naming
        if self.path.rstrip("/") == "/api/review-notes":   # [c]
            try:
                length = int(self.headers.get("Content-Length") or 0)
                payload = json.loads(self.rfile.read(length).decode("utf-8")) if 0 < length <= MAX_BODY_BYTES else None
            except (ValueError, UnicodeDecodeError):
                payload = None
            if not isinstance(payload, dict) or not isinstance(payload.get("page"), str) or not isinstance(payload.get("notes"), dict):
                self.send_error(400, "Expected {page, notes}")
                return
            notes = _merge_review_notes(payload["page"], payload["notes"])
            self._send_json({"ok": True, "count": sum(1 for n in notes.values() if not n.get("deleted"))})
            logger.info("Saved review notes for %s (%d)", payload["page"], len(notes))
            return
        if self.path.rstrip("/") != "/api/annotations":
            self.send_error(404, "Unknown endpoint")
            return

        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self.send_error(400, "Bad Content-Length")
            return
        if length <= 0 or length > MAX_BODY_BYTES:
            self.send_error(400, "Bad body size")
            return

        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self.send_error(400, "Body is not JSON")
            return
        if not isinstance(payload, dict):
            self.send_error(400, "Body is not an object")
            return

        stored = _merge_annotations(payload)
        # Refresh each conference's seed so a reload shows the merged state.
        for conference_dir in sorted(p for p in SITE_ROOT.glob("*") if p.is_dir()):
            write_annotations_seed(conference_dir)

        body = json.dumps({"ok": True, "count": len(stored.get("papers", {}))}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        logger.info("Saved %d marks to %s", len(stored.get("papers", {})), annotations_path())

    def log_message(self, fmt: str, *args: Any) -> None:
        logger.debug(fmt, *args)


def main() -> int:
    setup_logging()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8800)
    parser.add_argument("--host", default="127.0.0.1",  # [c]
                        help="Address to listen on; 0.0.0.0 opens it to the LAN (anyone there can edit marks).")
    parser.add_argument("--no-browser", action="store_true", help="Do not open a browser window.")
    args = parser.parse_args()

    if not SITE_ROOT.exists():
        logger.error("No site/ directory yet. Run update_database.py first.")
        return 1

    handler = partial(AnnotationHandler, directory=str(SITE_ROOT))
    url = f"http://localhost:{args.port}/"
    with ThreadingHTTPServer((args.host, args.port), handler) as httpd:  # [c]
        logger.info("Serving %s at %s  (Ctrl+C to stop)", SITE_ROOT, url)
        logger.info("Marks save to %s", annotations_path())
        if not args.no_browser:
            webbrowser.open(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            logger.info("Stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
