"""Pure impact signals: authority, actionability, and how they combine.

No database, no network, no model — every function here maps text (or an already
loaded row's fields) to a number in 0–1, so each is testable on its own and the
whole pass is deterministic. The storage-facing pass lives in
:mod:`archiver.analysis.classify`.

The design rule that matters: **components are stored, the total is derived.**
A single opaque 0.68 is impossible to trust and impossible to debug. Keeping
authority, topic, actionability, corroboration and market sensitivity on the row
lets the dashboard explain a ranking ("executive order, tariff language, names
Boeing, four outlets") and lets you retune the weights with one UPDATE instead
of re-running every model pass.
"""

from __future__ import annotations

import re
from typing import Any

# ── weights ───────────────────────────────────────────────────────────────────
# A starting position, not a result. The validation loop — do top-tier items
# precede larger moves in the tickers they name? — is what earns these numbers.
WEIGHTS: dict[str, float] = {
    "authority": 0.30,
    "corroboration": 0.25,
    "topic": 0.20,
    "actionability": 0.15,
    "market_sensitivity": 0.10,
}

# v2: sector-aware market sensitivity, and a full re-score after the
# Federal Register metadata repair (restored rows keep their content hash).
WEIGHTS_VERSION = "v2"

# ── authority ─────────────────────────────────────────────────────────────────
# Did Trump *do* this, or did someone report on it? Federal Register subtypes
# grade the first case further: an executive order carries the force of law, a
# proclamation is usually ceremonial, a notice is administrative housekeeping.
_SUBTYPE_AUTHORITY: dict[str, float] = {
    "executive order": 1.00,
    "presidential memorandum": 0.80,
    "memorandum": 0.80,
    "determination": 0.75,
    "proclamation": 0.65,
    "notice": 0.50,
    "order": 0.75,
}

_SOURCE_AUTHORITY: dict[str, float] = {
    "federal_register": 0.85,        # refined by subtype below
    "presidential_documents": 0.70,
    "whitehouse": 0.65,
    "news": 0.35,                    # reporting about him, not him acting
}

_DEFAULT_AUTHORITY = 0.30

# Only these sources carry a document *subtype*. News rows put the publisher in
# the same ``raw["kind"]`` slot, so reading it as a subtype anywhere would label
# every CNBC article as a document of type "CNBC".
_SUBTYPED_SOURCES = frozenset({"federal_register", "presidential_documents", "whitehouse"})

_GENERIC_LABEL: dict[str, str] = {
    "federal_register": "Federal Register document",
    "presidential_documents": "presidential document",
    "whitehouse": "White House release",
    "news": "news coverage",
}


def authority_score(source: str | None, raw: Any = None) -> tuple[float, str]:
    """Return ``(score, label)`` for how authoritative a status is.

    ``label`` is the human-readable reason ("Executive Order", "news coverage"),
    stored so a ranking can explain itself rather than asserting a number.
    """
    src = (source or "").lower()
    base = _SOURCE_AUTHORITY.get(src, _DEFAULT_AUTHORITY)

    subtype = ""
    if isinstance(raw, dict) and src in _SUBTYPED_SOURCES:
        # Federal Register calls it "subtype"; GovInfo calls it "kind".
        subtype = str(raw.get("subtype") or raw.get("kind") or "").strip()

    if subtype:
        graded = _SUBTYPE_AUTHORITY.get(subtype.lower())
        return (graded, subtype) if graded is not None else (base, subtype)

    return base, _GENERIC_LABEL.get(src, src or "unknown")


def is_generic_label(label: str | None) -> bool:
    """True when a label only restates the source, adding nothing to explain a rank."""
    return label in _GENERIC_LABEL.values() if label else True


# ── actionability ─────────────────────────────────────────────────────────────
# The line between "this happened" and "someone thinks this might happen". This
# is what separates a signed 50% steel tariff from an article speculating about
# one, and no model is needed to see the difference.
_COMMITTED = (
    "signed", "signs", "has signed", "hereby", "is hereby ordered", "it is ordered",
    "executive order", "proclaims", "do proclaim", "imposed", "imposes",
    "will impose", "has ordered", "orders", "enacted", "takes effect",
    "effective immediately", "goes into effect", "announced", "announces",
    "issued", "issues", "authorized", "directs", "directed", "approved",
    "granted", "revoked", "terminated", "declared",
)

_SPECULATIVE = (
    "may", "might", "could", "reportedly", "sources say", "is considering",
    "considering", "weighing", "expected to", "is poised", "floated",
    "suggested", "hinted", "rumored", "reportedly weighing", "would likely",
    "analysts say", "critics say", "appears to", "seems to", "if approved",
    "proposed", "proposal", "draft",
)

def _cue_matcher(cues: tuple[str, ...]) -> re.Pattern[str]:
    """Compile one boundary-guarded alternation, longest cue first."""
    ordered = sorted(cues, key=len, reverse=True)
    body = "|".join(re.escape(c) for c in ordered)
    return re.compile(rf"(?<![A-Za-z])({body})(?![A-Za-z])", re.IGNORECASE)


_COMMITTED_RE = _cue_matcher(_COMMITTED)
_SPECULATIVE_RE = _cue_matcher(_SPECULATIVE)

# A number attached to a measure is the strongest actionability tell there is:
# "50% tariff" is a decision, "tariffs on steel" is a topic.
_MAGNITUDE_RE = re.compile(r"\b\d{1,3}(?:\.\d+)?\s?(?:percent|%)", re.IGNORECASE)
_EFFECTIVE_DATE_RE = re.compile(
    r"\beffective\s+(?:immediately|(?:on\s+)?(?:january|february|march|april|may|june|"
    r"july|august|september|october|november|december)\b|\d{1,2}[/-]\d{1,2})",
    re.IGNORECASE,
)

_NEUTRAL = 0.50
_STEP = 0.15
_BONUS = 0.20


def actionability_score(text: str) -> float:
    """Score 0–1 for how committed the language is.

    Starts neutral and moves in both directions, because absence of evidence is
    genuinely uninformative here: a bare Federal Register title ("Modifying the
    Grand Staircase-Escalante National Monument") is an executed action carrying
    no cue words at all, and should not be punished for that. Authority already
    covers what kind of document it is.
    """
    if not text:
        return _NEUTRAL

    committed = len({m.group(1).lower() for m in _COMMITTED_RE.finditer(text)})
    speculative = len({m.group(1).lower() for m in _SPECULATIVE_RE.finditer(text)})

    score = _NEUTRAL + _STEP * min(committed, 3) - _STEP * min(speculative, 3)

    if _MAGNITUDE_RE.search(text):
        score += _BONUS
    if _EFFECTIVE_DATE_RE.search(text):
        score += _BONUS

    return max(0.0, min(1.0, score))


# ── market sensitivity ────────────────────────────────────────────────────────
# Naming a listed company is the precondition; how charged the language is
# decides the rest. FinBERT is trained on financial news, so its polarity is the
# right magnitude to reach for — but it is optional, and a mention with no
# reading still counts for the base.
_MENTION_BASE = 0.60
_SENTIMENT_SPAN = 0.40


_SECTOR_BASE = 0.35


def market_sensitivity_score(
    ticker_count: int,
    sentiment_compound: float | None = None,
    *,
    sector_count: int = 0,
) -> float:
    """Score 0–1 for how market-relevant an item is.

    A named company is the strongest signal, but requiring one scored 99% of the
    archive at zero: policy items name sectors, not tickers. An implicated
    sector therefore carries its own weight, below a direct mention.
    """
    if ticker_count <= 0 and sector_count <= 0:
        return 0.0
    score = _MENTION_BASE if ticker_count > 0 else _SECTOR_BASE
    if sentiment_compound is not None:
        score += _SENTIMENT_SPAN * min(abs(sentiment_compound), 1.0)
    return max(0.0, min(1.0, score))


# ── combination ───────────────────────────────────────────────────────────────
# Tier thresholds for display. People act on "critical", not on 0.68.
TIERS: tuple[tuple[float, str], ...] = (
    (0.75, "critical"),
    (0.58, "high"),
    (0.40, "notable"),
    (0.00, "routine"),
)


def tier_for(score: float) -> str:
    """Bucket a 0–1 impact score into a display tier."""
    for threshold, name in TIERS:
        if score >= threshold:
            return name
    return "routine"


def combine(components: dict[str, float | None]) -> float:
    """Weighted 0–1 impact score over the components that have been computed.

    Components still missing (``None``) are *excluded and the remaining weights
    renormalized* — not treated as zero. Before the clustering pass runs there is
    no corroboration number for anything, and scoring every row as if it had been
    measured and found unsupported would rank the whole archive as routine.
    """
    usable = {
        key: value
        for key, value in components.items()
        if value is not None and key in WEIGHTS
    }
    if not usable:
        return 0.0
    total_weight = sum(WEIGHTS[key] for key in usable)
    if total_weight <= 0:
        return 0.0
    weighted = sum(WEIGHTS[key] * value for key, value in usable.items())
    return max(0.0, min(1.0, weighted / total_weight))
