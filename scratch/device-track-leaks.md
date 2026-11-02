# Why device papers leaked into the circuits collection

*2026-09-21. Triggered by Yi spotting three compact-model papers at the bottom
of ESSERC 2025's "Links" session.*

## What happened

ESSERC 2025 session 18, "Links", held seven papers. 14.1–14.4 are wireline
circuits (CDR, retimer, transmitter, on-chip link). 14.5–14.7 were device work:

- Modeling Advanced Magnetoresistive Memories
- Versatile Compact Verilog-A Model of a STT-MTJ
- Statistical Model for the Calculation of Conductance Variations of Memristive Devices

All three survived the circuits/devices filter and were visible in the HTML.

## Why the filter missed them

**The split was decided at session granularity.** `esserc_tracks.DEVICE_SESSIONS`
lists whole sessions to drop, judged by reading each session's papers. A
session named "Links" reads as unambiguously circuits, so it was cleared —
and nobody read to the bottom of it. `DEVICE_PAPERS` exists for papers inside
otherwise-circuits sessions, but it was populated opportunistically, not by a
systematic pass over every title.

Two structural properties made this invisible rather than merely wrong:

1. **The conference appends.** The device papers sat at the *end* of a circuits
   session (14.5–14.7 of 7). This is a pattern, not an accident — ESSERC pads
   circuits sessions with related device work. Anything that samples the start
   of a session will never see it.
2. **A hand list cannot report its own incompleteness.** Nothing compared the
   list against the data, so a missing entry and a correct list looked
   identical from the outside.

## The silent-no-op bug this exposed

`drop_device_content` matches a title prefix only when the normalised key is
at least 12 characters (`if len(k) >= 12`). The entry `"A 512 kb 0.069"`
normalises to `a512kb0069` — **10 characters**, below the floor. It therefore
matched nothing for its entire existence, and the paper it was meant to drop
was still in the collection. No error, no warning.

Verified: the entry is now `"A 512 kb 0.069 μm2 Logic 3T GCRAM"` and the paper
is dropped (esscirc 2025: 142 → 141 papers).

## What changed

- **`tools/audit_device_tracks.py`** — makes both failure modes visible. It
  reports list entries that are too short to match or that failed to remove
  their target, and screens every surviving paper for device vocabulary with
  no circuit metric. Flags are candidates to read, never verdicts. Run it
  after any change to the track lists.
- Measured result of the first run: **1 silent no-op entry** and **2 further
  leaked device papers in ESSERC 2024**, both inside the circuits-sounding
  session "Above One Decade BW Building Blocks":
  - Access region resistance in graphene Dirac-Source FETs
  - Understanding the impact of the dielectric layer in modulating the TER of FTJ devices
- ESSERC after the fixes: 2024 140 → 138 papers, 2025 145 → 141.

## The lesson

Session names are not evidence about the papers inside them. Any split that
must hold across a whole corpus has to be checked **per title**, and any
hand-maintained list needs a tool that tells you when it has gone stale —
otherwise its failures are indistinguishable from success.

The reverse error is worse than the one found here: a wrong entry silently
deletes a real circuits paper. The audit tool reports that direction too, and
it is the first thing to check after any list edit.
