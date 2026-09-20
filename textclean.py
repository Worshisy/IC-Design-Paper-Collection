"""
Clean up the legacy markup IEEE stores in older titles and abstracts.

Two problems, both measured across the 2026-09-20 corpus:

* **HTML entities left encoded** - 2,768 occurrences, mostly `&#39;` and
  `&#34;`. These used to render by accident because the templates had
  autoescape switched off; with autoescape on they would show literally.
* **Pre-Unicode IEEE markup** - 8,749 occurrences of `/spl mu/`, `/sub 2/`,
  `/sup 2/` and friends, concentrated in 2000-2006. `"0.6 /spl mu/m CMOS"`
  is meant to read `"0.6 µm CMOS"`.

Unknown tokens are deliberately left untouched rather than guessed at, so a
name this table does not know stays visible instead of turning into the wrong
character.
"""

from __future__ import annotations

import html
import re

# `/spl <name>/` -> character. Names follow the old ISO entity sets.
SPL_ENTITIES: dict[str, str] = {
    # Lowercase Greek
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ",
    "epsi": "ε", "epsiv": "ε", "zeta": "ζ", "eta": "η",
    "theta": "θ", "iota": "ι", "kappa": "κ", "lambda": "λ",
    "mu": "µ", "nu": "ν", "xi": "ξ", "pi": "π",
    "rho": "ρ", "sigma": "σ", "tau": "τ", "upsi": "υ",
    "phi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω",
    # Uppercase Greek
    "Alpha": "Α", "Beta": "Β", "Gamma": "Γ", "Delta": "Δ",
    "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ", "Pi": "Π",
    "Sigma": "Σ", "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
    # Relations and operators
    "times": "×", "divide": "÷", "plusmn": "±", "minus": "−",
    "middot": "·", "ne": "≠", "les": "≤", "ges": "≥",
    "le": "≤", "ge": "≥", "ap": "≈", "equiv": "≡",
    "sim": "∼", "infin": "∞", "radic": "√", "prop": "∝",
    "Lt": "≪", "Gt": "≫", "cup": "∪", "cap": "∩",
    "int": "∫", "sum": "∑", "prod": "∏", "part": "∂",
    "nabla": "∇", "isin": "∈", "notin": "∉", "sub": "⊂",
    "sup": "⊃", "and": "∧", "or": "∨", "forall": "∀",
    "exist": "∃", "empty": "∅",
    # Arrows
    "rarr": "→", "larr": "←", "uarr": "↑", "darr": "↓",
    "harr": "↔", "rArr": "⇒", "lArr": "⇐", "hArr": "⇔",
    # Shapes and marks
    "deg": "°", "reg": "®", "trade": "™", "copy": "©",
    "Aring": "Å", "aring": "å", "acute": "´", "uml": "¨",
    "tilde": "~", "bsol": "\\", "sol": "/", "square": "□",
    "utri": "△", "dtri": "▽", "circ": "∘", "bull": "•",
    "dagger": "†", "para": "¶", "sect": "§",
    "hellip": "…", "ndash": "–", "mdash": "—",
    "lsquo": "‘", "rsquo": "’", "ldquo": "“", "rdquo": "”",
    "frac12": "½", "frac14": "¼", "frac34": "¾",
    "prime": "′", "Prime": "″", "perp": "⊥", "ang": "∠",
    # Script letters
    "lscr": "ℓ", "Bscr": "ℬ", "Cscr": "\U0001d49e", "Escr": "ℰ",
    "Fscr": "ℱ", "Hscr": "ℋ", "Lscr": "ℒ", "Mscr": "ℳ",
    "Rscr": "ℛ",
}

_SUPERSCRIPTS = {
    "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴",
    "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹",
    "+": "⁺", "-": "⁻", "−": "⁻", "=": "⁼",
    "(": "⁽", ")": "⁾", "n": "ⁿ", "i": "ⁱ",
}

_SUBSCRIPTS = {
    "0": "₀", "1": "₁", "2": "₂", "3": "₃", "4": "₄",
    "5": "₅", "6": "₆", "7": "₇", "8": "₈", "9": "₉",
    "+": "₊", "-": "₋", "−": "₋", "=": "₌",
    "(": "₍", ")": "₎",
}

# Ordinal suffixes read better as plain text than as modifier letters.
_ORDINALS = {"st", "nd", "rd", "th"}

_SPL_RE = re.compile(r"/spl\s+([A-Za-z][A-Za-z0-9.]{0,20})/")
_SUPSUB_RE = re.compile(r"/(sub|sup)\s+([^/]{1,24})/")
# "2.8: A 210fps Image Signal Processor" - the colon form the prefix regex misses.
# The space after the colon and the letter that follows are load-bearing: they
# keep a turns ratio ("3.5:1 transformer") from being read as a paper number.
_NUMBER_PREFIX_RE = re.compile(r"^\s*(?P<num>\d{1,3}\.\d{1,3}):\s+(?=[A-Za-z])")


def _render_spl(match: re.Match[str]) -> str:
    name = match.group(1)
    replacement = SPL_ENTITIES.get(name)
    if replacement is not None:
        return replacement
    # Try a case-insensitive hit before giving up.
    for key, value in SPL_ENTITIES.items():
        if key.lower() == name.lower():
            return value
    return match.group(0)  # unknown: leave visible rather than guess


def _render_supsub(match: re.Match[str]) -> str:
    kind, raw = match.group(1), match.group(2).strip()
    if not raw:
        return ""

    table = _SUPERSCRIPTS if kind == "sup" else _SUBSCRIPTS
    if all(character in table for character in raw):
        return "".join(table[character] for character in raw)

    if kind == "sup" and raw.lower() in _ORDINALS:
        return raw  # "4/sup th/" -> "4th"
    if kind == "sup" and raw in {"TM", "(R)", "R"}:
        return {"TM": "™", "(R)": "®", "R": "®"}[raw]

    # Fall back to the notation an engineer would write by hand.
    return ("^" if kind == "sup" else "_") + raw


def clean_text(text: str | None) -> str:
    """Decode entities and convert legacy IEEE markup to real characters."""

    if not text:
        return ""

    # Entities first: a title may hold "&#38;" for an ampersand that later
    # markup depends on. Twice, because a few records are double-encoded.
    cleaned = html.unescape(text)
    if "&" in cleaned:
        once_more = html.unescape(cleaned)
        if once_more != cleaned:
            cleaned = once_more

    cleaned = _SPL_RE.sub(_render_spl, cleaned)
    cleaned = _SUPSUB_RE.sub(_render_supsub, cleaned)

    # Collapse whitespace the substitutions may have left behind.
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned.strip()


def split_number_prefix(title: str) -> tuple[str | None, str]:
    """
    Split a "2.8: Title" style prefix off a title.

    The main parser already handles "2.8 Title"; ISSCC 2025 introduced the
    colon form, which slipped through and left the number in the title text.
    Returns (number or None, remaining title).
    """

    match = _NUMBER_PREFIX_RE.match(title)
    if not match:
        return None, title
    return match.group("num"), title[match.end():].strip()


__all__ = ["clean_text", "split_number_prefix", "SPL_ENTITIES"]
