"""
Regression sweep for the front-matter rules in parser.py.

Run this after ANY change to SKIP_TITLES / SKIP_PREFIXES / SKIP_PATTERNS, and
before committing that change. It does two things:

1. Unit-checks a fixed list of titles that must / must not be filtered,
   including the real papers that earlier, looser rules wrongly ate.
2. Sweeps every stored paper and reports what the current rules would remove,
   so you can eyeball the long titles for false positives.

    D:\\anaconda3\\python.exe tools/audit_front_matter.py
    D:\\anaconda3\\python.exe tools/audit_front_matter.py --show-caught 80

Exit code is non-zero if any unit case fails.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from parser import _is_front_matter, _is_front_matter_record  # noqa: E402

# (record, title, must_be_filtered) - programme items are front matter only
# when authorless, so these need the record, not just the title.
RECORD_CASES: list[tuple[dict, str, bool]] = [
    ({"authors": []}, "Listing", True),
    ({"authors": []}, "Career Panel: Chip In for Change", True),
    ({"authors": []}, "Social events", True),
    ({"authors": []}, "Workshops", True),
    ({"authors": []}, "Workshop on analog telecom and circuit concepts", True),
    ({"authors": []}, "Panel sessions", True),
    ({"authors": []}, "Student research preview", True),
    ({"authors": []}, "Committee photos", True),
    ({"authors": []}, "Plenary Speaker 1: Wireless spectrum challenges", True),
    ({"authors": []}, "Maps", True),
    ({"abstract": "Advertisement: IEEE."}, "Introducing IEEE Collabratec", True),
    # Real papers and talks that must survive all of the above.
    ({"authors": [1] * 8}, "Panel-Sized TFT-LCD Column Driver", False),
    ({"authors": [1, 1]}, "Keynote speaker: Massive MIMO active antenna arrays", False),
    ({"authors": []}, "About-Face: A Reconfigurable Beamformer", False),
    ({"authors": []}, "Mapping Techniques for Neural Accelerators", False),
    ({"authors": []}, "Scheduler-Aware Memory Controller", False),
    ({"authors": []}, "A 28nm Schedule-Aware DVFS Controller", False),
    # Journal tutorials end in "tutorial" like programme listings do; 31 were dropped until 2026-11-10.  # [c]
    ({"authors": [1, 1, 1], "abstract": "x" * 400}, "RFIC Reuse Techniques to Enable Ultra-Low-Power IoT: A Tutorial", False),  # [c]
    ({"authors": [1, 1], "abstract": "x" * 400}, "Oscillator phase noise: a tutorial", False),  # [c]
    ({"authors": [], "abstract": "Provides an abstract for each of the tutorial presentations and a brief biography."}, "Tutorials", True),  # [c]
    ({"authors": [], "abstract": ""}, "ISSCC 2024 Tutorials", True),  # [c]
]

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# (title, must_be_filtered). The False cases matter most: each one is a real
# item that a previous version of the rules removed by mistake.
CASES: list[tuple[str, bool]] = [
    # --- must be filtered -------------------------------------------------
    ("Front Cover", True),
    ("Cover Page", True),
    ("Front Cover Page", True),
    ("[Blank page]", True),
    ("Blank page [back cover]", True),
    ("[Breaker page]", True),
    ("Table of Contents", True),
    ("Detailed author index", True),
    ("Affiliation index", True),
    ("Committees", True),
    ("Steering Committee / Advisory Board / Technical Program Committee", True),
    ("Welcome from the CICC Committee!", True),
    ("RFIC 2024 Cover Page", True),
    ("RFIC 2024 TOC", True),
    ("RFIC 2025 Abstract Page", True),
    ("RFIC 2024 Author Index", True),
    ("ISSCC 2011 timetable", True),
    ("ISSCC 2024", True),
    ("ISCAS 2013", True),
    ("VLSI Technology and Circuits 2023 Cover Page", True),
    ("[ISSCC 2021 Title Page]", True),
    ("IEEE copyright form", True),
    ("Copyright [2007 IEEE International Solid-State Circuits Conference]", True),
    ("IEEE Transactions on Microwave Theory and Techniques publication information", True),
    ("IEEE Journal of Solid-State Circuits information for authors", True),
    ("IEEE Transactions on Circuits and Systems-II: Express Briefs Information for authors", True),
    ("Have you visited lately? www.ieee.org [advertisement]", True),
    ("Advertisement - Why we joined", True),
    ("Editorial Board", True),
    ("Guest editorial", True),
    ("Session list", True),
    ("The end of indexes", True),
    ("ISSCC glossary", True),
    # Programme ephemera found by the 2026-09-20 per-source audits.
    ("Notes", True),
    ("Author list", True),
    ("Sponsors", True),
    ("CICC 2019 Sponsors", True),
    ("USB label", True),
    ("About Causal Productions", True),
    ("Paper withdrawn", True),
    ("Paper not available", True),
    ("Conference Space Layout", True),
    ("Contributor listings", True),
    ("Staff or society listings", True),
    ("San Francisco Marriott Hotel Location Maps", True),
    ("Message from the General Chair", True),
    ("Frequently asked questions", True),
    ("F1: Machine Learning Hardware", True),
    ("EE2: How to Save Lives with Circuits", True),
    ("Forum 3: The Path to 6G", True),
    ("ISSCC 2024 Panel Discussion", True),
    ("Tutorials [10 abstracts]", True),
    ("ISSCC 2026 ITPC EWAA Regional Subcommittee", True),
    ("Committee List", True),
    ("RFIC 2021 Steering Committee and External Support", True),
    ("IEEE MTT-S International Microwave Symposium 2004/Microwave Week", True),
    ("IMS panel sessions", True),
    ("Monday poster session", True),
    ("2004 IEEE Radio Frequency Integrated Circuits (RFIC) Symposium Cat. No. 04CH37535", True),

    # --- must NOT be filtered (real content) ------------------------------
    ("Watermarking-based copyright protection of sequential functions", False),
    ("A 55 mm/sup 2/ 256 Mb NROM flash memory with embedded microcontroller", False),
    ('[Authors\' reply to comments on "CMOS low-noise amplifier design optimization techniques"]', False),
    ("A Glossary of Terms for Sigma-Delta Converters", False),
    ("A Cover Page Detection Circuit for Document Scanners", False),
    ("Welcoming the new era of GaN power devices", False),
    ("A 28-nm FeFET Compute-in-Memory Macro With 64x64 Array Size", False),
    ("122.7 TOPS/W Stdcell-Based DNN Accelerator Based on Transition Density", False),
    ("A Panel Discussion Interface Circuit for Multi-Speaker Arrays", False),
    ("Notes on the Design of Low-Noise Amplifiers", False),
    ("A Sponsors-Free Randomness Extractor in 28nm CMOS", False),
    ("Registration-Free Image Alignment Processor for AR Glasses", False),
    ("A 7V/us Tutorial-Free Gate Driver for GaN FETs", False),
    # Session headers ending in "subcommittee" - a broad rule once deleted
    # 27 of ISSCC 2012's 28 headers.
    ("Session 3 overview: Processors: High performance digital subcommittee", False),
    ("Session 2 overview: High-bandwidth DRAM & PRAM: Memory subcommittee", False),
    ("ISSCC 2025 ITPC European Subcommittee", True),
    ("ISSCC 2026 ITPC EWAA (Europe, West Asia, Africa) Regional Subcommittee", True),
    # --- session headers must survive filtering ---------------------------
    ("Session 12 Overview: Data Converters", False),
    ("ISSCC 2024 Session 1 Overview: Plenary", False),
    ("Advanced MOSFET modeling - Session 2", False),
]


def run_unit_cases() -> int:
    failures = 0
    for title, should_filter in CASES:
        got = _is_front_matter(title)
        if got != should_filter:
            failures += 1
            print(f"  FAIL  filtered={got!s:5s} expected={should_filter!s:5s} | {title[:78]}")
    if failures:
        print(f"\n{failures} of {len(CASES)} unit cases FAILED.")
    else:
        print(f"All {len(CASES)} unit cases pass.")
    return failures


def sweep_stored_data(show_caught: int) -> None:
    output_root = PROJECT_ROOT / "output"
    if not output_root.exists():
        print("\nNo output/ directory yet - skipping the stored-data sweep.")
        return

    per_source: dict[str, list[int]] = {}
    caught: collections.Counter[str] = collections.Counter()

    for source_dir in sorted(output_root.iterdir()):
        json_dir = source_dir / "json"
        if not json_dir.is_dir():
            continue
        removed = kept = 0
        for path in sorted(json_dir.glob("*.json")):
            if not re.fullmatch(r"\d{4}", path.stem):
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            for session in data.get("sessions", []):
                for paper in session.get("papers", []):
                    title = (paper.get("title") or "").strip()
                    # Pass the abstract too: IEEE boilerplate abstracts identify
                    # front matter that no title rule would catch.
                    if _is_front_matter_record({"abstract": paper.get("abstract"), "authors": paper.get("authors")}, title):   # authors too, as the parser has them  # [c]
                        removed += 1
                        caught[title] += 1
                    else:
                        kept += 1
        if removed or kept:
            per_source[source_dir.name] = [removed, kept]

    if not per_source:
        print("\nNo stored papers found.")
        return

    print("\nWhat the current rules would remove from stored data:")
    total_removed = total_kept = 0
    for name, (removed, kept) in sorted(per_source.items()):
        total = removed + kept
        total_removed += removed
        total_kept += kept
        print(f"  {name:7s} {removed:5d} removed / {total:6d} stored  ({100 * removed / total:4.1f}%)")
    grand = total_removed + total_kept
    print(f"  {'TOTAL':7s} {total_removed:5d} removed / {grand:6d} stored  ({100 * total_removed / grand:4.1f}%)")

    # Long titles are where false positives hide - real papers have long names.
    longest = sorted(caught, key=len, reverse=True)[:show_caught]
    print(f"\nLongest titles removed (check these for false positives):")
    for title in longest:
        print(f"  {len(title):3d}  {title[:110]}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--show-caught", type=int, default=15,
                        help="How many of the longest removed titles to print (default: 15).")
    parser.add_argument("--skip-sweep", action="store_true", help="Run only the unit cases.")
    args = parser.parse_args()

    print("=" * 70)
    print("Front-matter rule audit")
    print("=" * 70)
    failures = run_unit_cases()
    if not args.skip_sweep:
        sweep_stored_data(args.show_caught)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
