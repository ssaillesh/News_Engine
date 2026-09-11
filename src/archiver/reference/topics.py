"""Curated topic lexicon + a precision-first matcher.

Same philosophy as :mod:`archiver.reference.tickers`, for the same reason: on a
corpus of political headlines, loose keyword matching is worse than no matching.
Bare ``trade`` fires on "trade show" and "tradeoff"; bare ``ruling`` fires on
"ruling party"; bare ``military`` fires on almost every foreign-policy sentence
without telling you anything. So every term here is either multi-word or
unambiguous on its own, matched under the same non-letter boundaries.

``supply chain`` was tried in ``tariffs_trade`` and removed: it was the single
most-matched term in the lexicon and almost every hit was a defense or
shipbuilding document ("Securing America's Defense Supply Chains"), not a trade
measure. It is the exact failure mode this module exists to avoid — do not
re-add it without a trade-context qualifier.

Each topic carries a ``weight`` — how much a hit typically means for real-world
impact. Tariffs move markets and bind companies immediately; an immigration
proclamation matters enormously but rarely reprices a stock the same day. The
weights are a starting position to be tuned against observed market moves, not a
finding; see ``DESIGN.md`` on the validation loop.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Topic:
    key: str
    label: str
    # Typical impact weight for a hit, 0–1. Tunable; see module docstring.
    weight: float
    # Distinctive strings denoting this topic. Matched case-insensitively under
    # non-letter boundaries; every entry must be unambiguous standing alone.
    terms: tuple[str, ...] = field(default_factory=tuple)


# ── the topic universe ────────────────────────────────────────────────────────
# Ordered by weight for readability only; match order is handled by the compiler.
_TOPICS: tuple[Topic, ...] = (
    Topic(
        "tariffs_trade",
        "Tariffs & trade",
        1.0,
        (
            "tariff", "tariffs", "trade war", "trade deficit", "trade agreement",
            "trade deal", "trade barrier", "import duty", "import duties",
            "customs duty", "customs duties", "anti-dumping", "antidumping",
            "countervailing duty", "countervailing duties", "export control",
            "export controls", "trade representative", "most favored nation",
            "section 232", "section 301", "usmca", "nafta", "trade sanctions",
            "import quota", "import quotas", "de minimis",
        ),
    ),
    Topic(
        "foreign_policy",
        "Foreign policy",
        0.9,
        (
            "sanctions", "sanctioned", "nato", "united nations", "security council",
            "peace deal", "peace agreement", "ceasefire", "cease-fire",
            "troop withdrawal", "airstrike", "air strike", "military strike",
            "arms sale", "arms deal", "treaty", "summit", "diplomatic relations",
            "ambassador", "state department", "foreign aid", "embargo",
        ),
    ),
    Topic(
        "defense",
        "Defense & security",
        0.8,
        (
            "defense spending", "defense budget", "pentagon", "joint chiefs",
            "national guard", "missile defense", "nuclear weapons", "nuclear arsenal",
            "homeland security", "war powers",
        ),
    ),
    Topic(
        "political_conflict",
        "Political conflict",
        0.7,
        (
            "impeachment", "impeached", "indictment", "indicted", "grand jury",
            "subpoena", "subpoenaed", "contempt of congress", "government shutdown",
            "filibuster", "primary challenge", "censure", "recount",
            "special counsel", "investigation into", "oversight committee",
            "no confidence", "election fraud", "voter fraud", "ballot challenge",
        ),
    ),
    Topic(
        "legal_judicial",
        "Legal & judicial",
        0.7,
        (
            "supreme court", "federal judge", "appeals court", "injunction",
            "restraining order", "court ruling", "court order", "lawsuit",
            "attorney general", "justice department", "pardon", "clemency",
            "commutation", "executive privilege", "consent decree",
        ),
    ),
    Topic(
        "immigration",
        "Immigration",
        0.6,
        (
            "deportation", "deported", "border wall", "asylum seeker",
            "asylum seekers", "travel ban", "refugee admissions", "green card",
            "visa restrictions", "immigration enforcement", "border security",
            "birthright citizenship",
        ),
    ),
    Topic(
        "energy_environment",
        "Energy & environment",
        0.6,
        (
            "offshore drilling", "oil pipeline", "paris agreement", "paris accord",
            "emissions standard", "emissions standards", "clean power",
            "drilling permit", "drilling permits", "strategic petroleum reserve",
            "energy independence", "carbon tax",
        ),
    ),
    Topic(
        "economy_fiscal",
        "Economy & fiscal",
        0.75,
        (
            "federal reserve", "interest rate", "interest rates", "inflation",
            "tax cut", "tax cuts", "tax increase", "debt ceiling", "budget deficit",
            "stimulus", "recession", "unemployment rate", "minimum wage",
            "stock market", "bailout",
        ),
    ),
)

TOPICS: dict[str, Topic] = {t.key: t for t in _TOPICS}

# term(lower) → topic key, longest term first so "trade agreement" wins over
# "trade war" would-be overlaps and "import duties" beats "import duty".
_TERM_TO_TOPIC: dict[str, str] = {}
for _t in _TOPICS:
    for _term in _t.terms:
        _TERM_TO_TOPIC[_term.lower()] = _t.key

_SORTED_TERMS = sorted(_TERM_TO_TOPIC, key=len, reverse=True)

_MATCHER = re.compile(
    r"(?<![A-Za-z])(" + "|".join(re.escape(t) for t in _SORTED_TERMS) + r")(?![A-Za-z])",
    re.IGNORECASE,
)


def find_topics(text: str) -> dict[str, str]:
    """Return ``{topic_key: first term that matched}`` for topics named in text.

    One entry per topic even when several of its terms appear; the matched term
    is kept for display ("matched on 'section 232'") and for auditing whichever
    term turns out to be the noisy one.
    """
    if not text:
        return {}
    found: dict[str, str] = {}
    for match in _MATCHER.finditer(text):
        term = match.group(1)
        found.setdefault(_TERM_TO_TOPIC[term.lower()], term)
    return found


def topic_weight(keys: list[str] | tuple[str, ...]) -> float:
    """Combined 0–1 topic weight for a status: the heaviest topic present.

    Deliberately *max*, not sum. An item about both tariffs and immigration is
    not twice as consequential as one about tariffs; it is a tariff story that
    also touches immigration. Summing would let a scattershot article that
    glances off five topics outrank a focused executive order.
    """
    if not keys:
        return 0.0
    return max(TOPICS[k].weight for k in keys if k in TOPICS)
