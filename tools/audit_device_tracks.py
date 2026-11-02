"""
Check the circuits/devices split for the merged conferences.

ESSERC (2024+) and VLSI (2022+) each publish one proceedings holding two
tracks. Neither labels them, so the split is carried by hand-written lists in
`esserc_tracks.py` and `data/vlsi_technology_papers.txt`. A hand list has two
silent failure modes, and this tool makes both visible:

  * a **stale entry** that matches nothing - a session renamed, a title
    retyped - drops nothing and says nothing;
  * a **missing entry** leaves device papers in the collection. They hide in
    sessions whose name reads as circuits, so reading session names does not
    find them. ESSERC 2025's "Links" session ended with three compact-model
    papers for exactly this reason.

The screen below is deliberately noisy: it reports candidates to be read, not
a verdict. A title is flagged when it carries device vocabulary and none of
the chip metrics a circuits paper reports.

Run after any change to the track lists:
    python tools/audit_device_tracks.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import esserc_tracks  # noqa: E402
import vlsi_tracks  # noqa: E402
from config import get_config  # noqa: E402

# Process and physics results - what a device paper reports.
DEVICE_TERMS = (
    "compact model", "verilog-a", "tcad", "spice model", "device model",
    "mobility", "subthreshold slope", "gate stack", "gate-all-around",
    "nanosheet", "finfet", "gaa", "euv", "epitaxial", "wafer bonding",
    "monolayer", "2d material", "mos2", "graphene", "carbon nanotube",
    "ferroelectric", "fefet", "memristor", "memristive", "rram", "pcm cell",
    "mtj", "stt-mram", "magnetoresistive", "endurance", "retention",
    "conductance variation", "variability", "reliability", "degradation",
    "bti", "hot carrier", "leakage current", "dielectric", "hemt", "gan device",
    "silicon carbide", "doping", "junction", "channel length", "interface trap",
    "low-frequency noise", "flicker noise characteriz", "characterization of",
)

# Chip and system metrics - what a circuits paper reports.
CIRCUIT_TERMS = (
    "gb/s", "gs/s", "mb/s", "ms/s", "tops/w", "gops", "sndr", "enob", "sfdr",
    "phase noise", "pj/bit", "pj/b", "fj/", "dbm", "dbc", "mm2", "mw", "uw",
    "µw", "nw", "ppm", "adc", "dac", "pll", "dll", "vco", "lna", "pa ",
    "power amplifier", "transceiver", "receiver", "transmitter", "sram macro",
    "dc-dc", "ldo", "regulator", "beamform", "radar", "sensor interface",
    "readout", "serdes", "cdr", "equalizer", "oscillator", "frequency synthes",
)


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def _load(conference_id: str, year: int) -> dict | None:
    path = get_config(conference_id, create_dirs=False).json_dir / f"{year}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def check_esserc_lists() -> int:
    """Report ESSERC list entries that match nothing in the data."""

    problems = 0
    print("=" * 72)
    print("ESSERC track lists")
    print("=" * 72)

    for year, names in sorted(esserc_tracks.DEVICE_SESSIONS.items()):
        data = _load("esscirc", year)
        if data is None:
            print(f"  {year}: no data file")
            continue
        present = {_norm(s.get("session_name", "")) for s in data.get("sessions", [])}
        # A session already dropped is absent, which is the expected state, so
        # this only reports names that never matched anything at all.
        for name in sorted(names):
            if _norm(name) not in present:
                print(f"  {year}: session {name!r} matches nothing (dropped already, or stale)")

    for year, titles in sorted(esserc_tracks.DEVICE_PAPERS.items()):
        data = _load("esscirc", year)
        if data is None:
            continue
        keys = [
            _norm(p.get("title", ""))
            for s in data.get("sessions", [])
            for p in s.get("papers", [])
        ]
        for title in titles:
            key = _norm(title)
            if len(key) < 12:
                print(f"  {year}: {title!r} is too short to match (needs 12+ characters)")
                problems += 1
            elif any(k.startswith(key) for k in keys):
                print(f"  {year}: {title!r} STILL PRESENT - the filter did not remove it")
                problems += 1
    return problems


def screen_for_device_papers() -> int:
    """Flag surviving papers that read like device work, for a human to judge."""

    flagged = 0
    for conference_id, years in (("esscirc", (2024, 2025)), ("vlsi", (2022, 2023, 2024, 2025, 2026))):
        for year in years:
            data = _load(conference_id, year)
            if data is None:
                continue
            hits = []
            for session in data.get("sessions", []):
                for paper in session.get("papers", []):
                    title = (paper.get("title") or "").lower()
                    device = [t for t in DEVICE_TERMS if t in title]
                    circuit = [t for t in CIRCUIT_TERMS if t in title]
                    if device and not circuit:
                        hits.append((session.get("session_name", ""), paper, device))
            if hits:
                print()
                print("=" * 72)
                print(f"{conference_id} {year}: {len(hits)} paper(s) to read")
                print("=" * 72)
                for session_name, paper, device in hits:
                    print(f"  [{session_name}] {paper.get('article_number')}")
                    print(f"      {paper.get('title')}")
                    print(f"      device vocabulary: {', '.join(device[:4])}")
                flagged += len(hits)
    return flagged


def main() -> int:
    stale = check_esserc_lists()
    flagged = screen_for_device_papers()
    print()
    print("=" * 72)
    print(f"{stale} list problem(s); {flagged} paper(s) flagged for reading")
    print("Flags are candidates, not verdicts - read each title before acting.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
