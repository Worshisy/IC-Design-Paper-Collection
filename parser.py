from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from models import ConferenceYear, Paper, Session
from textclean import clean_text, split_number_prefix


logger = logging.getLogger(__name__)


# Matches session header titles returned by the IEEE Xplore API, such as:
#   "Session 1 Overview: Plenary"
#   "Session 2 Overview: Processors"
#   "ISSCC 2024 Session 3 Overview: Wearable Systems"
#   "Session 3 overview / RF: RF techniques"
#   "Session 7 overview - multimedia processing"
SESSION_HEADER_RE = re.compile(
    r"""
    (?:^.*?\s)?                 # optional prefix like "ISSCC 2024 "
    Session\s+
    (?P<number>\d+)
    \s*
    (?:Overview\s*)?
    [:\-–/]?\s*
    (?P<name>.+?)?
    \s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)

# CICC 2004-style headers put " - Session N" at the end, e.g.:
#   "Advanced MOSFET modeling - Session 2"
CICC_SESSION_TRAILER_RE = re.compile(
    r"""
    ^\s*
    (?P<name>.+?)
    \s*[-:]\s*
    Session\s+
    (?P<number>\d+)
    \s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Matches a paper number prefix at the beginning of an article title, such as:
#   "2.1 AMD Instinct MI350 Series GPUs ..."
#   "14.3 A 28nm 17.83-to-62.84TFLOPS/W Broadcast..."
PAPER_PREFIX_RE = re.compile(
    r"""^
    \s*
    (?P<num>\d+\.\d+)
    \s+
    (?P<title>.+)
    $
    """,
    re.VERBOSE,
)

# Titles to skip - structural front matter, not actual papers.
# These rules run for every conference AND journal, so keep entries generic;
# anchor anything source-specific in SKIP_PATTERNS instead.
SKIP_TITLES = frozenset({
    # Covers and boilerplate pages.
    "front cover", "back cover", "cover page", "front matter", "back matter",
    "copyright page", "copyright", "copyright notice", "copyright form",
    "ieee copyright form", "title page", "blank page",
    # Contents and indexes.
    "table of contents", "contents", "toc", "index",
    "author index", "index to authors", "affiliation index", "subject index",
    "the end of indexes", "author information page",
    # Committees.
    "committee", "committees", "steering committee", "organizing committee",
    "program committee", "executive committee", "technical program committee",
    "international technical program committee",
    # Editorial / society boilerplate (journals).
    "editorial", "guest editorial", "editorial board", "society information",
    "society staff", "publication information", "the editor's corner",
    "editor's corner", "information for authors", "instructions for authors",
    "information for contributors", "list of reviewers", "reviewers",
    "advertisement",
    # Programme material.
    "program file", "program at a glance", "program-at-a-glance",
    "abstract cards", "abstract page", "session list", "tutorials",
    # Misc.
    "awards", "award", "reflections", "dedication", "welcome", "welcome!",
    "foreword", "low-power analog signal processing",
    # Programme ephemera seen across RFIC / CICC / ISSCC audits.
    "notes", "author list", "sponsors", "sponsor", "usb label",
    "about causal productions", "paper withdrawn", "paper not available",
    "conference space layout", "contributor listings", "staff or society listings",
    "monday poster session", "tuesday poster session", "wednesday poster session",
    "index author", "detailed author index", "brief author index",
    "hub page", "opinion", "teaser abstract", "breaker page",
    # Enumerated from the rendered pages, 2026-09-21.
    "index of authors", "index to authors", "detailed author index",
    "conference timetable", "conference layout", "conference space layout",
    "technical co-sponsors", "joint plenary talks", "joint plenary speakers",
    "keynote speakers", "keynote papers", "invited papers", "contributed papers",
    "chairs' message", "chairs message", "organizers", "cover", "ad page",
    "student forum", "student research preview", "girafe forum",
    "educational events - tutorials", "reflections", "foreward",
    "paper withdrawn by author", "[paper withdrawn by author]",
    "pdf not available [paper withdrawn by author]",
    "isscc awards", "isscc aards", "isscc glossary",
    # Conference logistics, enumerated from the rendered pages 2026-09-21.
    "about page", "about cp", "[about cp]", "hub page", "end breaker",
    "abstracts cards", "[pdf viewing instructions]", "[org committee photos]",
    "committee photos", "conference overview", "conference schedule",
    "floor map", "session quick index", "guest program", "technical program",
    "program booklet", "full program", "program schedule", "rfic schedule",
    "rfic program", "educational session", "educational sessions",
    "luncheon talk", "plenary speakers", "vlsi forum", "preface",
    "[causal productions]", "about causal productions",
    "[announcements: future conferences]", "information on future special issues",
    "[paper not available", "paper not available", "m-12 withdrawn",
    "social events/guest program", "workshops and short courses",
    # Journal boilerplate enumerated from the rendered pages.
    "paper submission", "best paper award", "predoctoral achievement awards",
    "call for fellow nominations", "solid-state circuits newsletter",
    "editori-in-chief call for applicants", "editor-in-chief call for applicants",
    # IEEE house adverts. Recent ones carry no abstract at all, so the
    # "Advertisement:" prefix rule cannot see them.
    "myieee", "join ieee", "ieee access", "ieee dataport", "open access",
    "ieee open access publishing", "ieee xplore digital library",
    "introducing ieee collabratec", "introducing ieee collabratex",
    "ieee order form for reprints", "women in engineering",
    "ieee women in engineering", "ieee woen in engineering",
    "connect. support. inspire.", "thank you for your authorship",
    "together, we are advancing technology",
    "put your technology leadership in writing",
    "how can you get your idea to market first",
    "ieee foundation", "proceedings of the ieee",
    "member get-a-member (mgm) program",
    # Conference logistics pages (VLSI symposia in particular).
    "program", "floor map", "session quick index", "conference schedule",
    "rump sessions", "acknowledgement", "acknowledgment", "preface",
    "landing page", "ataglance", "at a glance", "society related material",
    "plenary session", "panel discussion program", "special workshop program",
    "demo session & reception", "evening panel discussion",
})

# Title prefixes that indicate non-paper entries.
SKIP_PREFIXES = (
    "tutorial:",
    "short course:",
    "foreword",
    "[front",
    "[back",
    "[title page",
    "[copyright",
    "[blank",
    "blank page",
    "executive committee",
    "international technical program committee",
    "program committee",
    "time table",
    "timetable",
)

# Front-matter nouns that follow an "<ACRONYM> <YEAR> " prefix, e.g.
# "RFIC 2024 Cover Page". Deliberately excludes "Session N ..." so that real
# session headers ("ISSCC 2024 Session 1 Overview: ...") are never skipped.
_CONF_FRONT_MATTER_NOUNS = (
    r"cover(?:\s+page)?|toc|table\s+of\s+contents|author\s+index|"
    r"affiliation\s+index|subject\s+index|index|abstract\s+cards?|"
    r"abstract\s+page|session\s+list|the\s+end\s+of\s+indexes|"
    r"author\s+information\s+page|steering\s+committee|committees?|"
    r"program.*|time\s*table|plenary\s+speaker.*|awards?|glossary|"
    r"sponsors?|committee\s+list|"
    r"welcome.*|front\s+matter|back\s+matter"
)

# Patterns for non-paper entries. Generic across sources - no conference
# acronym is hardcoded, so adding a new conference needs no change here.
SKIP_PATTERNS = (
    # "<ACRONYM> <YEAR> <front-matter noun>" e.g. "RFIC 2024 Cover Page".
    re.compile(
        rf"^[a-z][a-z\-.]{{1,12}}\s+\d{{4}}\s+(?:{_CONF_FRONT_MATTER_NOUNS})$",
        re.IGNORECASE,
    ),
    # Bare "<ACRONYM> <YEAR>" with nothing else, e.g. "ISSCC 2024".
    re.compile(r"^[a-z][a-z\-.]{1,12}\s+\d{4}$", re.IGNORECASE),
    # Bracketed front matter: "[Blank page]", "[Front cover]", "[Breaker page]".
    # Keyword-gated so bracketed scholarly items (authors' replies, comments)
    # are not mistaken for front matter.
    re.compile(
        r"^\[(?:blank|breaker|front|back|inside|cover|title|copyright|"
        r"table\s+of\s+contents|advertisement|index|pdf\s+reader)\b",
        re.IGNORECASE,
    ),
    # Journal mastheads / boilerplate, which carry the full journal name.
    re.compile(r"\b(?:information|instructions)\s+for\s+(?:authors|contributors)\b", re.IGNORECASE),
    re.compile(r"\bpublication\s+information\b", re.IGNORECASE),
    re.compile(r"\bsociety\s+(?:information|staff)\b", re.IGNORECASE),
    re.compile(r"\beditorial\s+board\b", re.IGNORECASE),
    # "copyright" only as boilerplate, never mid-title (real papers discuss it).
    re.compile(r"\bcopyright\s+(?:form|page|notice|transfer)\b", re.IGNORECASE),
    re.compile(r"\btable\s+of\s+contents\b", re.IGNORECASE),
    re.compile(r"(?:author|affiliation|subject)\s+index$", re.IGNORECASE),
    re.compile(r"call for papers$", re.IGNORECASE),
    re.compile(r"\bglossary$", re.IGNORECASE),
    re.compile(r"^\d{4}\s+IEEE\s+International", re.IGNORECASE),
    re.compile(r"^\d{4}\s+program", re.IGNORECASE),
    re.compile(r"^the\s+editor'?s\s+corner$", re.IGNORECASE),
    re.compile(r"^(?:guest\s+)?editorial$", re.IGNORECASE),
    re.compile(r"^welcome\b", re.IGNORECASE),
    re.compile(r"\[advertisement\]", re.IGNORECASE),
    re.compile(r"^advertisement\b", re.IGNORECASE),
    re.compile(r"cover page\]?$", re.IGNORECASE),
    re.compile(r"title page\]?$", re.IGNORECASE),
    re.compile(r"^steering committee\b", re.IGNORECASE),
    re.compile(r"^copyright\b", re.IGNORECASE),
    # --- enumerated from the rendered pages, 2026-09-21 (second pass) ---
    # RFIC 2013/2014 embed their own session index as fake papers:
    # "Session: RMO1A: Low-power pulse-based radios".
    re.compile(r"^session\s*:\s*\S+\s*:", re.IGNORECASE),
    # USB/CD media artwork and wrappers.
    re.compile(r"^\[?(?:usb|cd)\b.*(?:label|welcome|art)", re.IGNORECASE),
    re.compile(r"^\[?about\s+cp\b", re.IGNORECASE),
    re.compile(r"\bhub\s+page$", re.IGNORECASE),
    re.compile(r"\bbreaker\s+page$", re.IGNORECASE),
    re.compile(r"\bguest\s+program$", re.IGNORECASE),
    re.compile(r"\bopinion$", re.IGNORECASE),
    # Programme / schedule / map documents whatever the prefix.
    re.compile(r"\b(?:technical\s+program|program\s+booklet|full\s+program|"
               r"program\s+schedule|conference\s+schedule|floor\s+maps?|"
               r"session\s+quick\s+index)\b", re.IGNORECASE),
    re.compile(r"^\w+\s+schedule\s*\d{0,4}$", re.IGNORECASE),
    # Committee listings that name the conference first.
    re.compile(r"\bconference\s*\([A-Z]+\)\s*committees$", re.IGNORECASE),
    re.compile(r"\bsymposium\s+committees$", re.IGNORECASE),
    re.compile(r"\bcommittees$", re.IGNORECASE),
    # Withdrawn / unavailable placeholders.
    re.compile(r"^\[?paper\s+not\s+available", re.IGNORECASE),
    re.compile(r"^[a-z]-?\d+\s+withdrawn$", re.IGNORECASE),
    # Educational sessions and short courses as programme entries.
    re.compile(r"\beducational\s+sessions?\b", re.IGNORECASE),
    re.compile(r"\bshort\s+course\s+program\b", re.IGNORECASE),
    re.compile(r"\bsunday\s+workshop\b|\bfriday\s+forum\b", re.IGNORECASE),
    # Journal: annual index volumes, with or without the spaces IEEE drops.
    re.compile(r"^\d{4}\s*index\s*ieee\b", re.IGNORECASE),
    # Journal: membership and society promotion.
    re.compile(r"\bmembership\s+application$", re.IGNORECASE),
    re.compile(r"^ieee\s+membership\s+can\s+help", re.IGNORECASE),
    re.compile(r"^expand\s+your\s+professional\s+network", re.IGNORECASE),
    re.compile(r"^join\s+ieee\b", re.IGNORECASE),
    re.compile(r"^celebrating\s+the\s+vitality\s+of\s+technology", re.IGNORECASE),
    re.compile(r"\bundergraduate/pre-?graduate\s+scholarships$", re.IGNORECASE),
    re.compile(r"\bwomen\s+in\s+engineering\s+advertisement\]", re.IGNORECASE),
    # Journal: calls for papers and special-issue announcements. These carry
    # IEEE's "Describes the above-named upcoming special issue" boilerplate,
    # so the abstract rule catches most; this covers the ones with none.
    re.compile(r"^call\s+for\s+(?:papers|nominations|applicants)\b", re.IGNORECASE),
    re.compile(r"^special\s+issue\s+(?:on|for|metamaterials)\b", re.IGNORECASE),
    re.compile(r"\bcall\s+for\s+papers\]?$", re.IGNORECASE),
    re.compile(r"^\d{4}\s+mtt-s\s+awards$", re.IGNORECASE),
    # --- enumerated from the rendered pages, 2026-09-21 ---
    # Awards round-ups, including IEEE's own "Aards" typo and bracketed counts.
    re.compile(r"^(?:isscc\s+)?a[aw]ards?\b", re.IGNORECASE),
    re.compile(r"\baards?\s*&|\bawards?\s*&\s*ieee", re.IGNORECASE),
    # Short courses, tutorials, workshops and forums as programme entries.
    re.compile(r"^short\s+course\b", re.IGNORECASE),
    re.compile(r"^workshop\s+on\b", re.IGNORECASE),
    re.compile(r"\btutorials?$", re.IGNORECASE),
    re.compile(r"^(?:isscc|rfic|cicc|esscirc|esserc|a-?sscc)\s*\d{4}\s+(?:tutorial|short\s+course|forum|index|conference|breaker|reflections|foreword|forward|preface|program|awards?|ad\s+page|cover|organizers)", re.IGNORECASE),  # [c]
    re.compile(r"^es\d*\s*:\s*student\s+research", re.IGNORECASE),
    re.compile(r"^se\d+\s", re.IGNORECASE),
    re.compile(r"^td\s*:\s", re.IGNORECASE),
    # Withdrawn-paper placeholders.
    re.compile(r"withdrawn\s+by\s+(?:author|isscc)", re.IGNORECASE),
    re.compile(r"^pdf\s+not\s+available", re.IGNORECASE),
    # Committee / subcommittee listings in any phrasing.
    re.compile(r"\bitpc\b.*\bsubcommittee\b", re.IGNORECASE),
    # NOT a bare "...subcommittee$": ISSCC session headers end that way
    # ("Session 3 overview: Processors: High performance digital subcommittee").
    re.compile(r"\b(?:itpc|regional|technical\sprogram)\b[^:]*\bsubcommittee$", re.IGNORECASE),
    # Glossaries and keyword indexes.
    # Anchored: "ISSCC glossary" is front matter, "A Glossary of Terms for
    # Sigma-Delta Converters" is a real paper.
    re.compile(r"\bglossary$", re.IGNORECASE),
    re.compile(r"\[keyword\s+index\]|\[acronym\s+list\]", re.IGNORECASE),
    # Anniversary / history material.
    re.compile(r"^\d{1,3}\s+years\s+of\b", re.IGNORECASE),
    re.compile(r"^history\s+of\s+papers\b", re.IGNORECASE),
    re.compile(r"anniversary\s+(?:photos|author\s+honor\s+roll)", re.IGNORECASE),
    # Online-proceedings wrapper records.
    re.compile(r"\bon\s*line\s+proceedings$", re.IGNORECASE),
    re.compile(r"^esscirc\s+\d{4}\s*-\s*ieee\s+\d+(?:st|nd|rd|th)\s+european", re.IGNORECASE),
    re.compile(r"^\d{4}\s*index\b", re.IGNORECASE),
    re.compile(r"^patents?\s+abstracts?$", re.IGNORECASE),
    re.compile(r"^\d{4}\s+ieee\s+membership\s+form", re.IGNORECASE),
    re.compile(r"^\d{4}\s+reviewers?\s+list$", re.IGNORECASE),
    re.compile(r"^techrxiv\b", re.IGNORECASE),
    re.compile(r"^short\s+course\s*\d*$", re.IGNORECASE),
    re.compile(r"^\d{4}\s+symposium\s+on\s+vlsi", re.IGNORECASE),
    re.compile(r"^\d{4}\s+(?:ieee\s+)?asian\s+solid[\s-]*state\s+circuits\s+conference",  # [c]
               re.IGNORECASE),
    re.compile(r"\btechnical\s+sess(?:ion|oin)s?$", re.IGNORECASE),
    re.compile(r"\blist of reviewers\b", re.IGNORECASE),
    re.compile(r"^\d{4}\s+list of reviewers", re.IGNORECASE),
    re.compile(r"^(?:first|second|final)\s+(?:announcement\s+and\s+)?call\s+for\s+papers", re.IGNORECASE),
    # Programme items that are not authored papers: forums, panels, evening
    # events, social events, tutorials round-ups, short courses.
    re.compile(r"^(?:f|ee|se|sc|t)\d+\s*:", re.IGNORECASE),
    re.compile(r"^(?:forum|evening\s+event|social\s+event|panel|panel\s+discussion|"
               r"short\s+course|tutorial)\s*\d*\s*:", re.IGNORECASE),
    re.compile(r"\bpanel\s+discussion$", re.IGNORECASE),
    re.compile(r"\[\s*panel\s+discussions?\s*\]$", re.IGNORECASE),  # [c]
    re.compile(r"^(?:tutorials|short\s+courses|forums|evening\s+events)\b", re.IGNORECASE),
    re.compile(r"\[\s*\d+\s+abstracts?\s*\]$", re.IGNORECASE),
    # Venue / logistics pages.
    re.compile(r"\b(?:hotel|venue)\s+(?:location\s+)?maps?$", re.IGNORECASE),
    re.compile(r"\blocation\s+maps?$", re.IGNORECASE),
    re.compile(r"^registration\s+(?:desk|information|form|fees?|page|hours)\b", re.IGNORECASE),
    re.compile(r"^message\s+from\b", re.IGNORECASE),
    re.compile(r"^frequently\s+asked\s+questions", re.IGNORECASE),
    # Committee and organisation listings in any phrasing.
    re.compile(r"\b(?:steering|executive|organizing|organising|technical\s+program|"
               r"program)\s+commit+ee", re.IGNORECASE),
    re.compile(r"\bregional\s+subcommittee$", re.IGNORECASE),
    re.compile(r"\bcommittee\s+list$", re.IGNORECASE),
    # Catalogue / proceedings-record entries.
    re.compile(r"\bcat\.?\s*no\.", re.IGNORECASE),
    re.compile(r"^proceedings\s+of\s+the\b.*\b(?:conference|symposium)\b",
               re.IGNORECASE),
    re.compile(r"\bdigest\s+of\s+technical\s+papers\s*$", re.IGNORECASE),
    # Co-located events that are not this conference's papers.
    re.compile(r"^(?:ims|mtt-s)\b", re.IGNORECASE),
    re.compile(r"\bmicrowave\s+week\b", re.IGNORECASE),
    # --- enumerated from the Unassigned buckets, 2026-09-21 ---
    # Bracketed programme placeholders: "[Opinion]", "[Teaser abstract]".
    re.compile(r"^\[(?:opinion|teaser abstract)\]$", re.IGNORECASE),
    # Workshop and panel codes RFIC prints as though they were papers:
    # "WSA: Advances in ...", "RPM-A: Who will win ...", "RPTU-A: ...".
    re.compile(r"^(?:ws|rpm|rptu|rtu)[a-z]?(?:-[a-z0-9])?\s*:\s", re.IGNORECASE),
    # Panels, fora and round tables.
    re.compile(r"^round\s+table\b", re.IGNORECASE),
    re.compile(r"\b(?:forum|panel\s+session|round\s+table)$", re.IGNORECASE),
    # Bare plenary-speaker placeholders. A plenary WITH a talk title after the
    # colon is a real talk and is left alone.
    re.compile(r"^plenary\s+speakers?\s*\d*$", re.IGNORECASE),
    # Venue and logistics.
    re.compile(r"\bconvention\s+cent(?:er|re)\s+maps?$", re.IGNORECASE),
    re.compile(r"\bsymposium\s+activities$", re.IGNORECASE),
    # Poster/breaker separator pages.
    re.compile(r"\bposter\s+session\s*\[breaker\s+page\]$", re.IGNORECASE),
)

# Abstracts IEEE attaches to front matter. Far more reliable than the title
# heuristics above: these are fixed boilerplate strings, so they identify
# covers/indexes/committee pages whatever the title happens to say.
FRONT_MATTER_ABSTRACTS = (
    "presents the front cover",
    "presents the back cover",
    "presents the title page",
    "presents the table of contents",
    "author index contains an entry",
    "intended for user notes",
    "provides a listing of current committee",
    "provides a listing of the officers",
    "prospective authors are requested",
    "these instructions give guidelines",
    "presents a listing of sponsors",
    "describes the above-named publication",
    # Found by the SSCL audit; the same boilerplate is used by every journal.
    "provides a listing of current staff",
    "presents a listing of the editorial board",
    "describes the above-named upcoming conference",
    "presents information on the ieee",
    "presents the subject index",
    "presents the author index",
    "presents the subject/author index",
    "presents a listing of the current",
)

# Abstracts that START with one of these are never papers. IEEE writes them
# verbatim for adverts, conference notices and special-issue calls; matching
# the prefix rather than a substring keeps a real abstract that merely uses the
# word "advertisement" safe.
FRONT_MATTER_ABSTRACT_PREFIXES = (
    # Section dividers: "Start of the above-titled section of the conference
    # proceedings record." ISSCC 2006 files five of these as papers.
    "start of the above-titled section",
    "start of the above titled section",
    # Short courses and tutorials, whose text is never published. Note that
    # "summary form only given" on its own is NOT a marker - IEEE puts it on
    # real digest papers too, so it is paired with a course marker below.
    "provides an abstract of the tutorial presentation",
    "provides an abstract of the short course",
    # Forward-looking event listings.
    "provides a listing of upcoming conference events",

    "advertisement",
    "provides notice of upcoming conference",
    "provides notice of upcoming special issue",
    "provides a listing of the editors",
    "provides a listing of current staff",
    "presents a listing of the editorial board",
    "lists the reviewers who contributed",
    "the publication offers a note of thanks and lists its reviewers",
    "presents the front cover",
    "presents the back cover",
)

# Used only for short titles: one real paper (a 2018 CICC terahertz radio)
# carries this auto-generated keyword-list abstract, and must not be dropped.
KEYWORD_LIST_ABSTRACT = "the following topics are dealt with"

# A record whose abstract begins like this IS a session heading, not a paper:
# "Presents an overview of the above titled session held at the conference".
# ISSCC 2006 carries 31 of them and no programme PDF at all, so this is the
# only structure that year has.
SESSION_OVERVIEW_ABSTRACT = "presents an overview of the above titled session"

# Programme items - schedules, panels, social events - listed among the
# papers. Treated as front matter ONLY when the record has no authors: a real
# paper called "Panel-Sized TFT-LCD Column Driver" (8 authors) and an invited
# "Keynote speaker: Massive MIMO ..." (2 authors) must both survive.
# Roman-numeral page numbers mark front matter (i, iv, xvii, ...).
ROMAN_PAGE_RE = re.compile(r"^[ivxlcdm]+$", re.IGNORECASE)

PROGRAMME_TITLE_RE = re.compile(
    r"^(?:"
    r"listing|schedule|maps?|about|registration|transportation|"
    r"workshops?|workshop\s+on|panel\s+sessions?|"
    r"social(?:\s+and\s+special)?\s+events?|special\s+events?|"
    r"poster\s+sessions?|student\s+research\s+preview|"
    r"industry\s+showcase|committee\s+photos?|"
    r"special\s+session|career\s+panel|"
    r"plenary\s+session|plenary,|foreward|demo\s+session|"
    r"networking|closing\s+remarks?|opening\s+remarks?|"
    r"advance\s+programs?|sessions|floor\s*plans?|traffic\s+flow|"  # [c]
    r"conference\s+site\s+maps?|panel\s+discussions?|pd-?\d+"  # [c]
    r")(?=$|[\s:,.])",   # not \b: that matches before a hyphen,
                             # turning "About-Face: A ..." into front matter
    re.IGNORECASE,
)


# Programme items - schedules, panels, social events - that are listed among
# the papers. These are only front matter when the record has NO authors: a
# real paper called "Panel-Sized TFT-LCD Column Driver" (8 authors) and an
# invited "Keynote speaker: Massive MIMO ..." (2 authors) must both survive.


def _normalize_whitespace(text: str) -> str:
    """Collapse internal whitespace to single spaces and strip ends."""

    return re.sub(r"\s+", " ", text).strip()


# IEEE appends layout markers to some session headers: 25 of ISSCC 2002's
# 26 sessions came through as 'image sensors [breaker page]'.
SESSION_NAME_NOISE_RE = re.compile(
    r"\s*\[(?:breaker\s*page|continued|cont\.?|front\s*cover|back\s*cover)\]\s*$",
    re.IGNORECASE,
)


def _clean_session_name(raw_name: Optional[str]) -> str:
    """Normalise a session name: drop Overview:, layout markers, old markup."""

    if not raw_name:
        return ""
    name = raw_name.strip()
    name = re.sub(r"^Overview\s*[:\-–]\s*", "", name, flags=re.IGNORECASE)
    # CICC titles its session records "Session 2 - Low power analog" with an em
    # dash the header regex leaves behind, so the name arrived as "- Low power
    # analog" - which then failed every plausibility check downstream.
    name = re.sub(r"^[\s:\-–—]+", "", name)
    name = SESSION_NAME_NOISE_RE.sub("", name)
    # Session names never went through this, so legacy markup showed on the
    # page: "filters and continuous-time /spl Delta//spl Sigma/ converters".
    return clean_text(name).strip()

def _is_front_matter(title: str) -> bool:
    """Check whether the title indicates structural front matter or non-paper content."""

    lower = title.lower().strip()
    if lower in SKIP_TITLES:
        return True
    if any(lower.startswith(prefix) for prefix in SKIP_PREFIXES):
        return True
    if any(pat.search(lower) for pat in SKIP_PATTERNS):
        return True
    return False


def _is_front_matter_record(rec: Dict[str, Any], title: str) -> bool:
    """
    Front-matter test with the abstract available.

    Falls back to the title rules, then checks IEEE's fixed boilerplate
    abstracts, which catch covers/indexes/committee pages that no title rule
    would recognise.
    """

    # A parseable session header is structure, never front matter. Without
    # this guard a broad rule silently deletes a year's session skeleton -
    # "\bsubcommittee$" once removed 27 of ISSCC 2012's 28 headers, which end
    # "...: Memory subcommittee".
    if _parse_session_header(title) is not None:
        return False

    if _is_front_matter(title):
        return True

    # Front matter is paginated in roman numerals; a real paper never is.
    # ISSCC 2006 files a Foreword and three essays on iii/xiii/xv/xvii.
    start_page = str(rec.get("startPage") or "").strip()
    if start_page and not start_page[0].isdigit() and ROMAN_PAGE_RE.match(start_page):
        return True

    # Authorless programme items (schedules, panels, social events).
    if not rec.get("authors") and PROGRAMME_TITLE_RE.match(title.strip()):
        return True

    abstract = (rec.get("abstract") or "").strip().lower()
    if not abstract:
        return False

    head = abstract[:160]
    # A short course or tutorial, not a paper. Both halves are required: the
    # first phrase alone appears on real digest papers.
    if abstract.startswith("summary form only given") and any(
        marker in head for marker in ("short course", "this tutorial", "the tutorial")
    ):
        return True

    if abstract.startswith(FRONT_MATTER_ABSTRACT_PREFIXES):
        return True
    if any(marker in head for marker in FRONT_MATTER_ABSTRACTS):
        return True
    # Auto-generated keyword lists mark front matter, except on a real paper -
    # which is always long-titled, so require a short title here.
    if KEYWORD_LIST_ABSTRACT in head and len(title) < 80:
        return True
    return False


def _parse_session_header(title: str) -> Optional[Tuple[int, str]]:
    """
    Try to parse a session header from an article title.

    Returns (session_number, session_name) or None.
    """

    # Try CICC style first so that "Advanced MOSFET modeling - Session 2"
    # yields a non-empty session name.
    m2 = CICC_SESSION_TRAILER_RE.match(title)
    if m2:
        num = int(m2.group("number"))
        name = _clean_session_name(m2.group("name"))
        return num, name

    m = SESSION_HEADER_RE.match(title)
    if m:
        num = int(m.group("number"))
        name = _clean_session_name(m.group("name"))
        return num, name

    return None


# "Session MO1A: Integrated Mixers I" (RFIC 2004). The code is alphanumeric,
# so SESSION_HEADER_RE, which wants digits, never matched these and they were
# counted as papers.
ALPHA_SESSION_HEADER_RE = re.compile(
    r"^\s*Session\s+(?P<code>[A-Z][A-Z0-9]{1,5})\s*[:\-\u2013]\s*(?P<name>.+?)\s*$",
    re.IGNORECASE,
)


def _parse_alpha_session_header(title: str) -> Optional[Tuple[str, str]]:
    """Return (session_code, session_name) for alphanumeric session headers."""

    match = ALPHA_SESSION_HEADER_RE.match(title)
    if not match:
        return None
    return match.group("code").upper(), _clean_session_name(match.group("name"))


def _sort_records_by_page(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Sort API records by startPage so session headers appear before their
    papers.  For some years the API returns session overview records grouped
    at the end; page-number sorting fixes the interleaving.
    """

    def _page_key(rec: Dict[str, Any]) -> int:
        try:
            return int(rec.get("startPage", 99999))
        except (ValueError, TypeError):
            return 99999

    return sorted(records, key=_page_key)


def _choose_conference_record_order(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Choose the safest order for conference parsing.

    IEEE API ordering varies by year:
    - Some years already have correct header/paper stream order (keep original).
    - Some years push many session headers to the tail (use start-page sort).
    """

    titled_records: List[Tuple[int, str]] = []
    for idx, rec in enumerate(records):
        raw_title = (rec.get("articleTitle") or "").strip()
        if not raw_title or _is_front_matter(raw_title):
            continue
        titled_records.append((idx, raw_title))

    if not titled_records:
        return records

    header_positions: List[int] = []
    header_numbers: List[int] = []
    for pos, (_, title) in enumerate(titled_records):
        header = _parse_session_header(title)
        if header is None:
            continue
        header_positions.append(pos)
        header_numbers.append(header[0])

    if not header_positions:
        return _sort_records_by_page(records)

    total = len(titled_records)
    first_header_pos = header_positions[0]
    last_header_pos = header_positions[-1]
    unique_header_count = len(set(header_numbers))
    increasing_headers = all(
        header_numbers[i] <= header_numbers[i + 1]
        for i in range(len(header_numbers) - 1)
    )

    # If headers start early and are well distributed/increasing, trust original
    # API order (better for un-prefixed papers).
    has_good_original_order = (
        unique_header_count >= 8
        and first_header_pos <= max(15, int(0.25 * total))
        and last_header_pos >= int(0.60 * total)
        and increasing_headers
    )
    if has_good_original_order:
        return records

    return _sort_records_by_page(records)


def _extract_paper(
    rec: Dict[str, Any],
    raw_title: str,
    year: int,
    session: Session,
    paper_index: int,
    conference_name: str,
    conference_dates: str,
    conference_location: str,
) -> Paper:
    """Build a Paper object from a single API record."""

    inferred_number = f"{session.session_number}.{paper_index}"

    displayed_number: Optional[str] = None
    title = raw_title

    # "2.8: Title" (ISSCC 2025 onwards) as well as the older "2.8 Title".
    colon_number, stripped = split_number_prefix(title)
    if colon_number:
        displayed_number = colon_number
        title = stripped

    prefix_match = PAPER_PREFIX_RE.match(title)
    if prefix_match:
        displayed_number = prefix_match.group("num")
        title = prefix_match.group("title").strip()

    if displayed_number:
        if displayed_number != inferred_number:
            logger.debug(
                "Paper number mismatch in session %s: displayed=%s, inferred=%s, title=%r",
                session.session_number, displayed_number, inferred_number, title,
            )

    authors: List[str] = []
    for author_obj in rec.get("authors", []):
        name = author_obj.get("preferredName") or author_obj.get("normalizedName", "")
        if name:
            authors.append(name)

    html_link = rec.get("htmlLink", "")
    paper_url: Optional[str] = None
    if html_link:
        paper_url = (
            f"https://ieeexplore.ieee.org{html_link}"
            if html_link.startswith("/") else html_link
        )

    return Paper(
        year=year,
        session_number=session.session_number,
        session_name=session.session_name,
        paper_number=inferred_number,
        inferred_paper_number=inferred_number,
        title=clean_text(title),
        abstract=clean_text(rec.get("abstract", "")),
        authors=authors,
        affiliations=[],
        author_affiliations_raw="",
        conference_name=conference_name,
        conference_dates=conference_dates,
        conference_location=conference_location,
        displayed_paper_number=displayed_number,
        paper_url=paper_url,
        doi=rec.get("doi"),
        article_number=str(rec.get("articleNumber") or "") or None,
        start_page=str(rec.get("startPage") or "") or None,
        citation_count=citation_count(rec),  # [c]
    )


def citation_count(rec: Dict[str, Any]) -> Optional[int]:  # [c]
    """IEEE's citationCount as an int; None when the record has none."""

    try:
        return int(rec.get("citationCount"))
    except (TypeError, ValueError):
        return None


def _paper_prefix_session_number(raw_title: str) -> Optional[int]:
    """Return the session number from a leading paper prefix like '12.3 ...'."""

    m = PAPER_PREFIX_RE.match(raw_title)
    if not m:
        return None
    prefix = m.group("num")
    try:
        return int(prefix.split(".", 1)[0])
    except (ValueError, IndexError):
        return None


def build_conference_year_from_api(
    records: List[Dict[str, Any]],
    year: int,
    proceedings_url: str,
    publication_number: str,
    conference_name: str = "",
    conference_dates: str = "",
    conference_location: str = "",
    group_by_issue: bool = False,
) -> ConferenceYear:
    """
    Build a ConferenceYear model from IEEE Xplore search API records.

    Handles multiple data layouts across different ISSCC years:
    - Years with session headers interspersed among papers
    - Years where session headers are grouped at the end (sorted by page)
    - Years with no session headers at all (single-session fallback)
    """

    sorted_records = _sort_records_by_page(records) if group_by_issue else _choose_conference_record_order(records)

    sessions: List[Session] = []

    # Journal mode (e.g. JSSC): group by issue / isNumber instead of sessions.
    if group_by_issue:
        issue_to_session: Dict[Tuple[Any, Any, Any], Session] = {}
        for rec in sorted_records:
            raw_title = rec.get("articleTitle", "").strip()
            if not raw_title:
                continue

            if not conference_name:
                conference_name = rec.get("publicationTitle", "")
            if not conference_dates:
                conference_dates = rec.get("publicationDate", "")

            if _is_front_matter_record(rec, raw_title):
                continue

            issue_num = rec.get("issue")
            volume = rec.get("volume")
            is_number = rec.get("isNumber")

            # Early-access papers (online first) appear under a special
            # "PP/99" combination in JSSC. Group them into a dedicated
            # "Early Access" pseudo-issue instead of treating them like a
            # normal numbered issue.
            is_early = bool(rec.get("isEarlyAccess")) or str(volume).upper() == "PP" or issue_num == 99
            if is_early:
                key = ("EA", None, None)
            else:
                key = (volume, issue_num, is_number)

            if key not in issue_to_session:
                session_number = len(issue_to_session) + 1
                if is_early:
                    session_name = "Early Access"
                elif volume and issue_num:
                    session_name = f"Vol. {volume}, Issue {issue_num}"
                elif volume:
                    session_name = f"Vol. {volume}"
                elif issue_num:
                    session_name = f"Issue {issue_num}"
                else:
                    session_name = "Issue"
                session = Session(
                    session_number=session_number,
                    session_code=str(session_number),
                    session_name=session_name,
                )
                issue_to_session[key] = session
                sessions.append(session)

            session = issue_to_session[key]
            idx_within_issue = len(session.papers) + 1
            paper = _extract_paper(
                rec,
                raw_title,
                year,
                session,
                idx_within_issue,
                conference_name,
                conference_dates,
                conference_location,
            )
            session.papers.append(paper)

    else:
        current_session: Optional[Session] = None
        overview_counter = 0
        unsorted_papers: List[Tuple[Dict[str, Any], str]] = []
        sessions_by_number: Dict[int, Session] = {}

        def _get_or_create_session(session_number: int, session_name: str = "") -> Session:
            existing = sessions_by_number.get(session_number)
            if existing is not None:
                # If we created a placeholder earlier and later discover a real name,
                # prefer the explicit header name.
                if session_name and (
                    not existing.session_name
                    or existing.session_name.lower().startswith("session ")
                ):
                    existing.session_name = session_name
                return existing

            name = session_name or f"Session {session_number}"
            created = Session(
                session_number=session_number,
                session_code=str(session_number),
                session_name=name,
            )
            sessions_by_number[session_number] = created
            sessions.append(created)
            return created

        # Only trust a "12.3 ..." title prefix as a session marker when this
        # year genuinely uses session headers. Without the guard, a performance
        # figure in a title ("122.7 TOPS/W ...", VLSI 2024) invents session 122
        # and swallows the whole proceedings.
        has_session_headers = any(
            _parse_session_header(title) is not None
            or _parse_alpha_session_header(title) is not None
            for title in (
                (rec.get("articleTitle") or "").strip() for rec in sorted_records
            )
            if title and not _is_front_matter(title)
        )

        for rec in sorted_records:
            raw_title = rec.get("articleTitle", "").strip()
            if not raw_title:
                continue

            if not conference_name:
                conference_name = rec.get("publicationTitle", "")
            if not conference_dates:
                conference_dates = rec.get("publicationDate", "")

            if _is_front_matter_record(rec, raw_title):
                continue

            # A session-overview record defines a session; its title is the
            # session name.
            if SESSION_OVERVIEW_ABSTRACT in (rec.get("abstract") or "").lower():
                overview_counter += 1
                current_session = _get_or_create_session(
                    overview_counter, _clean_session_name(raw_title)
                )
                continue

            header = _parse_session_header(raw_title)
            if header is not None:
                session_number, session_name = header
                current_session = _get_or_create_session(session_number, session_name)
                logger.debug("Detected session header: %s (number=%s)", raw_title, session_number)
                continue

            # "Session MO1A: Integrated Mixers I" - alphanumeric code, so it
            # gets the next free sequential number and keeps its printed code.
            alpha_header = _parse_alpha_session_header(raw_title)
            if alpha_header is not None:
                code, session_name = alpha_header
                session_number = max(sessions_by_number, default=0) + 1
                current_session = _get_or_create_session(session_number, session_name)
                current_session.session_code = code
                logger.debug("Detected alphanumeric session header: %s", raw_title)
                continue

            # If a title includes an explicit paper prefix like "14.2 ...", use the
            # prefix's major number as the owning session. This guards against years
            # where API record ordering is imperfect and headers/papers are interleaved.
            prefix_session_number = (
                _paper_prefix_session_number(raw_title) if has_session_headers else None
            )
            if prefix_session_number is not None:
                current_session = _get_or_create_session(prefix_session_number)

            if current_session is None:
                unsorted_papers.append((rec, raw_title))
                continue

            paper_index_within_session = len(current_session.papers) + 1
            paper = _extract_paper(
                rec, raw_title, year, current_session, paper_index_within_session,
                conference_name, conference_dates, conference_location,
            )
            current_session.papers.append(paper)

        # Fallback: if no session headers were found, put all papers in session 1.
        if not sessions and unsorted_papers:
            logger.info(
                "[%s] No session headers found; assigning %d papers to a single session",
                year, len(unsorted_papers),
            )
            fallback_session = Session(
                session_number=1,
                session_code="1",
                session_name="General",
            )
            sessions.append(fallback_session)
            for idx, (rec, raw_title) in enumerate(unsorted_papers, start=1):
                paper = _extract_paper(
                    rec, raw_title, year, fallback_session, idx,
                    conference_name, conference_dates, conference_location,
                )
                fallback_session.papers.append(paper)
        elif unsorted_papers:
            # Papers appeared before the first session header (rare after page sort).
            logger.warning(
                "[%s] %d papers appeared before any session header; prepending to session 1",
                year, len(unsorted_papers),
            )
            first_session = sessions[0]
            prepend: List[Paper] = []
            for idx, (rec, raw_title) in enumerate(unsorted_papers, start=1):
                paper = _extract_paper(
                    rec, raw_title, year, first_session, idx,
                    conference_name, conference_dates, conference_location,
                )
                prepend.append(paper)
            offset = len(prepend)
            for p in first_session.papers:
                new_idx = int(p.paper_number.split(".")[-1]) + offset
                p.paper_number = f"{first_session.session_number}.{new_idx}"
                p.inferred_paper_number = p.paper_number
            first_session.papers = prepend + first_session.papers

        # Keep conference sessions ordered by numeric session id.
        if sessions:
            sessions.sort(key=lambda s: s.session_number)

    if group_by_issue:
        _sort_sessions_by_issue(sessions)

    conference = ConferenceYear(
        year=year,
        proceedings_url=proceedings_url,
        sessions=sessions,
        conference_name=conference_name or None,
        conference_dates=conference_dates or None,
        conference_location=conference_location or None,
    )

    _deduplicate_papers(conference)
    _validate_conference_year(conference)
    return conference


def _sort_sessions_by_issue(sessions: List[Session]) -> None:
    """
    Put journal issues in calendar order and renumber them.

    The API returns December first in several years (JSSC 2002/2003/2021,
    TCAS-II 2019-2025), which left issues out of order on the page and made
    each paper's "<session>.<n>" prefix disagree with the issue it sits in.
    Early Access stays last whatever its key.
    """

    def key(session: Session) -> Tuple[int, float, float]:
        name = session.session_name or ""
        if name.lower().startswith("early"):
            return (1, 0.0, 0.0)
        volume = re.search(r"Vol\.\s*(\d+)", name)
        issue = re.search(r"Issue\s*(\d+)", name)
        return (
            0,
            float(volume.group(1)) if volume else float("inf"),
            float(issue.group(1)) if issue else float("inf"),
        )

    sessions.sort(key=key)

    # TMTT returns some issues as two separate batches under one label; fold
    # them back together so an issue appears once.
    merged: List[Session] = []
    for session in sessions:
        if merged and merged[-1].session_name == session.session_name:
            merged[-1].papers.extend(session.papers)
            continue
        merged.append(session)
    sessions[:] = merged

    for position, session in enumerate(sessions, start=1):
        session.session_number = position
        session.session_code = str(position)
        for index, paper in enumerate(session.papers, start=1):
            number = f"{position}.{index}"
            paper.session_number = position
            paper.session_name = session.session_name
            paper.paper_number = number
            paper.inferred_paper_number = number


def _deduplicate_papers(conference: ConferenceYear) -> None:
    """
    Remove papers that appear twice in the same year.

    ISSCC 2002 returns 56 titles twice - once under a bare "Session 0" bucket
    and once under the real topical session, with different article numbers and
    one copy missing its abstract. Keep the better-populated copy, preferring
    the one that is not in a placeholder session, and renumber what is left.
    """

    best: Dict[str, Tuple[Session, Paper]] = {}
    drop: List[Tuple[Session, Paper]] = []

    for session in conference.sessions:
        for paper in session.papers:
            key = re.sub(r"\W+", " ", (paper.title or "").lower()).strip()
            if not key:
                continue
            previous = best.get(key)
            if previous is None:
                best[key] = (session, paper)
                continue

            previous_session, previous_paper = previous
            # Prefer a real session over session 0, then an abstract, then authors.
            def rank(sess: Session, pap: Paper) -> Tuple[int, int, int]:
                return (
                    1 if sess.session_number > 0 else 0,
                    1 if (pap.abstract or "").strip() else 0,
                    len(pap.authors or []),
                )

            if rank(session, paper) > rank(previous_session, previous_paper):
                best[key] = (session, paper)
                drop.append(previous)
            else:
                drop.append((session, paper))

    if not drop:
        return

    for session, paper in drop:
        try:
            session.papers.remove(paper)
        except ValueError:
            pass

    logger.info(
        "[%s] Removed %d duplicate paper record(s)", conference.year, len(drop)
    )

    conference.sessions = [s for s in conference.sessions if s.papers]
    for session in conference.sessions:
        for index, paper in enumerate(session.papers, start=1):
            number = f"{session.session_number}.{index}"
            paper.paper_number = number
            paper.inferred_paper_number = number


def _validate_conference_year(conference: ConferenceYear) -> None:
    """
    Run consistency checks on a parsed ConferenceYear.

    Logs warnings for issues; does not raise so the pipeline can continue.
    """

    last_session_number = 0
    for session in conference.sessions:
        if session.session_number <= last_session_number:
            logger.warning(
                "Session numbers not strictly increasing in year %s: found %s after %s",
                conference.year,
                session.session_number,
                last_session_number,
            )
        last_session_number = session.session_number

        if not session.papers:
            logger.warning(
                "Session %s (%s) has zero papers in year %s",
                session.session_number,
                session.session_name,
                conference.year,
            )
            continue

        expected_index = 1
        for paper in session.papers:
            expected_inferred = f"{session.session_number}.{expected_index}"
            if paper.inferred_paper_number != expected_inferred:
                logger.warning(
                    "Non-contiguous numbering in year %s session %s: expected %s, found %s",
                    conference.year,
                    session.session_number,
                    expected_inferred,
                    paper.inferred_paper_number,
                )
            expected_index += 1


__all__ = [
    "SESSION_HEADER_RE",
    "PAPER_PREFIX_RE",
    "build_conference_year_from_api",
]
