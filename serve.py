"""
Serve the generated site locally so paper marks save straight to disk.

Opening site/<id>/index.html directly from disk works too, but a file:// page
cannot write anything - marks then live only in that browser's localStorage
until you press "Export marks". Served over http, every like / mark / note is
POSTed here and written to userdata/annotations.json, which update_database.py
syncs to iCloud.

    python serve.py               # http://localhost:8800
    python serve.py --port 9000
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


class AnnotationHandler(SimpleHTTPRequestHandler):
    """Static file server plus a single POST endpoint for marks."""

    def do_POST(self) -> None:  # noqa: N802 - http.server naming
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
    parser.add_argument("--no-browser", action="store_true", help="Do not open a browser window.")
    args = parser.parse_args()

    if not SITE_ROOT.exists():
        logger.error("No site/ directory yet. Run update_database.py first.")
        return 1

    handler = partial(AnnotationHandler, directory=str(SITE_ROOT))
    url = f"http://localhost:{args.port}/"
    with ThreadingHTTPServer(("127.0.0.1", args.port), handler) as httpd:
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
