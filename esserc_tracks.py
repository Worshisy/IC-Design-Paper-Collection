"""
Which ESSERC sessions belong to the devices half, and are therefore dropped.

ESSERC (2024 onwards) merged ESSCIRC's circuits conference with ESSDERC's
device-research conference into one publication. Unlike VLSI, its programme
does not label the two tracks, so they cannot be separated structurally -
"Amplifiers" and "Advanced Silicon Devices" look alike to a parser.

The split below was made by reading every paper title in all 93 sessions and
judging each session on its content, not its name. Circuit papers report chip
metrics (GS/s, SNDR, TOPS/W, phase noise, efficiency); device papers report
process and physics results (mobility, subthreshold slope, gate stacks, TCAD,
endurance/retention of a cell).

Keyed by (year, session name) deliberately: "Advanced Memory Devices" is
wholly devices in 2025 but mixed in 2024, so a name-only key would be wrong.

ESSCIRC up to and including 2023 is the circuits conference outright, so
nothing here applies to those years.
"""

from __future__ import annotations

from typing import Dict, List, Set, Tuple

# Whole sessions that are device research.
DEVICE_SESSIONS: Dict[int, Set[str]] = {
    2024: {
        "Christian Enz",                      # compact MOSFET modelling keynote
        "Advanced Silicon Devices",
        "Advanced Materials for Logic Devices",
        "DTCO & System-Level Modeling",
        "Power & mmWave Devices",
        "Devices for Imaging",
        "Reliabilty & Characterization",      # IEEE's own spelling
        "Emerging Devices",
        "SOI Based Devices",
        "Modeling of Emerging Devices",
        "Compact Modeling",
    },
    2025: {
        "DTCO and STCO",
        "Emerging Computing Devices",
        "Advanced Memory Devices",
        "Advanced TCAD",
        "Emerging Memory",
        "Compact Modeling and Characterization",
        "In-Memory Computing Using Emerging Devices",
        "Advanced CMOS Devices",
    },
}

# Individual device papers inside otherwise-circuits sessions. Matched on a
# normalised prefix of the title, so LaTeX and punctuation do not matter.
DEVICE_PAPERS: Dict[int, List[str]] = {
    2024: [
        "N2 Nanosheet Pathfinding-PDK",
        "Integration of GAA Monolayer MoS2 Nanosheet FETs",
        "High Density 360",                    # aligned CNT FET
        "BEoL Varactors Based on HfO2/ZrO2 Superlattice",
        "Simplified EPFL HEMT Model",
        "Compact Model of Conductive-Metal-Oxide",
        "Cryogenic Front-to-Back Coupling in FD-SOI",
        "How Significant Is SET Programming Strategy",
        "A Reliable 2 bit MLC FeFET",
        "Understanding the Time Dependent Write and Read Performance",
        "A Novel DTCO-driven 1T1R Bitcell",
        "Highly Controllable Probabilistic Bits Leveraging Instability",
        "Implementation of FitzHugh-Nagumo Neurons",
    ],
    2025: [
        "Harnessing Turing Instability",
        "Low-Frequency Noise Characterization of Sub-",
        "A 40nm 48.7F2 Bit 1T2R Resistive Memory Bitcell Array",
        "A 512 kb 0.069",                      # logic 3T GCRAM
        "Stacking-Engineered HfO2-ZrO2 Superlattice",
        "Stacked 2D Monolayer",
        "Cryogenic Performance Assessment of FD-SOI Transistors",
        "Demonstration of Nanoscale Cryogenic Ferroelectric",
        "High-Precision Close-to-Analog Programming of PCM Cells",
        "Self-Selective Memristors for Real-Time Wireless",
        "Investigating Harmonic Distortion Dips",
        "Analysis of Substrate Impact on SP3T Switch",
        "Enhanced Monolithic Bidirectional Dual-Gate GaN HEMT",
        "Towards Ultra Low Thermo-Mechanical Sensitive Capacitors",
        "Highly Sensitive MXene/Si X-Ray Detector",
        "First Demonstration of IGO-IGZO Based In-Sensormemory",
    ],
}


def _key(text: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def drop_device_content(year: int, year_data: dict) -> Tuple[int, int]:
    """
    Remove device sessions and device papers for one ESSERC year.

    Returns (sessions_removed, papers_removed). A year with no entry here is
    left completely untouched, which covers every ESSCIRC year up to 2023.
    """

    device_sessions = DEVICE_SESSIONS.get(year)
    device_papers = DEVICE_PAPERS.get(year)
    if not device_sessions and not device_papers:
        return 0, 0

    session_keys = {_key(name) for name in (device_sessions or set())}
    paper_keys = [_key(title) for title in (device_papers or [])]

    kept_sessions = []
    removed_sessions = removed_papers = 0

    for session in year_data.get("sessions", []):
        if _key(session.get("session_name", "")) in session_keys:
            removed_sessions += 1
            removed_papers += len(session.get("papers", []))
            continue

        kept_papers = []
        for paper in session.get("papers", []):
            title_key = _key(paper.get("title", ""))
            if any(title_key.startswith(k) for k in paper_keys if len(k) >= 12):
                removed_papers += 1
                continue
            kept_papers.append(paper)

        if kept_papers:
            session["papers"] = kept_papers
            kept_sessions.append(session)
        else:
            removed_sessions += 1

    # Renumber what survives, keeping each session's printed code.
    for position, session in enumerate(kept_sessions, start=1):
        session["session_number"] = position
        for index, paper in enumerate(session["papers"], start=1):
            number = f"{position}.{index}"
            paper["session_number"] = position
            paper["session_name"] = session["session_name"]
            paper["paper_number"] = number
            paper["inferred_paper_number"] = number

    year_data["sessions"] = kept_sessions
    return removed_sessions, removed_papers


__all__ = ["drop_device_content", "DEVICE_SESSIONS", "DEVICE_PAPERS"]
