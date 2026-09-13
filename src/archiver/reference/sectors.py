"""Market sectors, the policy language that moves them, and a stance detector.

Company detection answers "who did Trump name". That is the wrong question most
of the time: an order imposing steel tariffs names no company at all, yet its
market read is obvious. This module answers the question that actually has an
answer on almost every item — **which part of the market does this touch, and in
which direction** — by matching policy vocabulary rather than corporate names.

Three pieces:

* **Sectors** carry the vocabulary that implicates them ("semiconductor",
  "drilling permit") plus a representative ETF and the watchlist tickers that sit
  inside them, so "what does this affect" always resolves to something tradable.
* **Stance** reads whether the action is restrictive or supportive *for the
  sector named* — a tariff is bad for importers, a deregulation is good for the
  operator. This is deliberately not sentiment: "Trump slams Boeing" and "Trump
  imposes tariffs on aircraft parts" carry the same market direction while
  reading very differently as prose.
* Both are curated and boundary-matched, following the precision rules in
  :mod:`archiver.reference.tickers` — a wrong sector is worse than none.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Stance values, in the vocabulary a reader would use.
RESTRICTIVE = "restrictive"   # tariffs, bans, probes — headwind for the sector
SUPPORTIVE = "supportive"     # exemptions, deregulation, awards — tailwind
MENTIONED = "mentioned"       # named, no clear direction


@dataclass(frozen=True, slots=True)
class Sector:
    key: str
    label: str
    # A liquid, well-known proxy so "which stock" always has an answer even when
    # no individual company is named.
    etf: str
    # Watchlist members that sit in this sector.
    tickers: tuple[str, ...] = field(default_factory=tuple)
    # Policy vocabulary that implicates the sector. Multi-word or unambiguous
    # only, matched under non-letter boundaries.
    terms: tuple[str, ...] = field(default_factory=tuple)


_SECTORS: tuple[Sector, ...] = (
    Sector(
        "materials", "Materials & Metals", "XLB", ("CAT",),
        (
            "steel", "aluminum", "aluminium", "copper", "lumber", "timber",
            "rare earth", "rare earths", "critical minerals", "cement",
            "smelter", "smelting", "mining", "iron ore", "nickel", "lithium",
        ),
    ),
    Sector(
        "industrials", "Industrials & Manufacturing", "XLI", ("CAT", "DE", "GE", "BA"),
        (
            "manufacturing", "factory", "factories", "industrial base",
            "shipbuilding", "machinery", "infrastructure", "construction",
            "supply chain", "reshoring", "onshoring", "domestic production",
            "assembly plant",
        ),
    ),
    Sector(
        "technology", "Technology", "XLK",
        ("AAPL", "MSFT", "NVDA", "INTC", "MU", "GOOGL", "META", "ORCL", "PLTR"),
        (
            "semiconductor", "semiconductors", "microchip", "microchips", "chipmaker",
            "artificial intelligence", "data center", "data centers", "cloud computing",
            "social media", "big tech", "antitrust", "export control", "export controls",
            "tiktok", "encryption", "quantum computing", "chips act",
        ),
    ),
    Sector(
        "energy", "Energy", "XLE", ("XOM", "CVX"),
        (
            "oil", "crude", "natural gas", "liquefied natural gas", "drilling",
            "drilling permit", "pipeline", "refinery", "refineries", "coal",
            "offshore leasing", "strategic petroleum reserve", "opec",
            "energy independence", "fracking", "gasoline prices",
        ),
    ),
    Sector(
        "healthcare", "Healthcare & Pharma", "XLV", ("PFE", "LLY", "MRNA", "UNH"),
        (
            "drug pricing", "prescription drug", "prescription drugs", "pharmaceutical",
            "pharmaceuticals", "generic drug", "generic drugs", "medicare", "medicaid",
            "vaccine", "vaccines", "clinical trial", "health insurance", "opioid",
            "food and drug administration",
        ),
    ),
    Sector(
        "financials", "Financials", "XLF", ("JPM", "GS", "WFC", "BAC"),
        (
            "federal reserve", "interest rate", "interest rates", "central bank",
            "banking regulation", "bank capital", "cryptocurrency", "bitcoin",
            "digital asset", "digital assets", "stablecoin", "capital gains",
            "debt ceiling", "treasury yields", "dodd-frank",
        ),
    ),
    Sector(
        "consumer", "Consumer & Retail", "XLY",
        ("AMZN", "WMT", "COST", "MCD", "SBUX", "NKE", "KO", "PEP", "HD", "DIS"),
        (
            "retailer", "retailers", "grocery", "groceries", "consumer prices",
            "cost of living", "household goods", "e-commerce", "shopping",
            "apparel", "footwear", "restaurant chain", "affordability",
        ),
    ),
    Sector(
        "defense", "Defense & Aerospace", "ITA", ("LMT", "BA"),
        (
            "defense contractor", "defense contractors", "defense spending",
            "defense budget", "weapons system", "weapons systems", "munitions",
            "fighter jet", "missile defense", "arms sale", "arms sales",
            "shipyard", "military procurement", "golden dome",
        ),
    ),
    Sector(
        "transport", "Transport & Autos", "IYT",
        ("F", "GM", "TSLA", "UAL", "AAL", "DAL", "HOG", "GT"),
        (
            "automaker", "automakers", "auto parts", "electric vehicle",
            "electric vehicles", "airline", "airlines", "air travel", "railroad",
            "trucking", "shipping", "port", "ports", "freight", "tariff on cars",
            "vehicle imports",
        ),
    ),
    Sector(
        "agriculture", "Agriculture & Food", "MOO", ("DE",),
        (
            "farmer", "farmers", "farm bill", "soybean", "soybeans", "corn crop",
            "wheat", "cattle", "beef", "poultry", "crop", "crops", "agriculture",
            "agricultural", "ethanol", "fertilizer", "food prices",
        ),
    ),
    Sector(
        "real_estate", "Real Estate & Housing", "XLRE", (),
        (
            "housing", "mortgage", "mortgage rates", "homebuilder", "homebuilders",
            "home prices", "rent control", "zoning", "affordable housing",
            "commercial real estate",
        ),
    ),
)

SECTORS: dict[str, Sector] = {s.key: s for s in _SECTORS}

_TERM_TO_SECTOR: dict[str, str] = {}
for _s in _SECTORS:
    for _t in _s.terms:
        _TERM_TO_SECTOR.setdefault(_t.lower(), _s.key)

_SORTED_TERMS = sorted(_TERM_TO_SECTOR, key=len, reverse=True)

_MATCHER = re.compile(
    r"(?<![A-Za-z])(" + "|".join(re.escape(t) for t in _SORTED_TERMS) + r")(?![A-Za-z])",
    re.IGNORECASE,
)


def find_sectors(text: str) -> dict[str, str]:
    """Return ``{sector_key: first term that matched}`` for sectors the text touches."""
    if not text:
        return {}
    found: dict[str, str] = {}
    for m in _MATCHER.finditer(text):
        term = m.group(1)
        found.setdefault(_TERM_TO_SECTOR[term.lower()], term)
    return found


# ── stance ────────────────────────────────────────────────────────────────────
# Direction *for the sector named*, not tone of voice. "Imposes tariffs on steel"
# is restrictive for steel importers however neutrally it is phrased.
_RESTRICTIVE_TERMS = (
    "tariff", "tariffs", "duties", "duty", "impose", "imposes", "imposing", "imposed",
    "restrict", "restricts", "restriction", "restrictions", "ban", "bans", "banned",
    "sanction", "sanctions", "sanctioned", "embargo", "quota", "quotas",
    "investigate", "investigation", "probe", "antitrust", "lawsuit", "sue", "sues",
    "sued", "fine", "fines", "fined", "penalty", "penalties", "crack down",
    "crackdown", "revoke", "revokes", "revoked", "terminate", "terminates",
    "suspend", "suspends", "suspended", "block", "blocks", "blocked", "curb",
    "curbs", "raise prices", "price controls", "export control", "export controls",
    "withdraw", "withdraws", "cut off", "halt", "halts",
)
_SUPPORTIVE_TERMS = (
    "exempt", "exempts", "exemption", "exemptions", "deregulate", "deregulation",
    "tax cut", "tax cuts", "approve", "approves", "approved", "approval",
    "invest", "investment", "investments", "subsidy", "subsidies", "grant",
    "grants", "award", "awards", "awarded", "boost", "boosts", "expand",
    "expands", "expansion", "incentive", "incentives", "streamline", "fast-track",
    "lower prices", "reduce prices", "relief", "waiver", "waivers", "unleash",
    "permitting reform", "open up", "reopen", "support for", "rebuild", "rebuilding",
)


def _cue_matcher(terms: tuple[str, ...]) -> re.Pattern[str]:
    body = "|".join(re.escape(t) for t in sorted(terms, key=len, reverse=True))
    return re.compile(rf"(?<![A-Za-z])({body})(?![A-Za-z])", re.IGNORECASE)


_RESTRICTIVE_RE = _cue_matcher(_RESTRICTIVE_TERMS)
_SUPPORTIVE_RE = _cue_matcher(_SUPPORTIVE_TERMS)


def detect_stance(text: str) -> tuple[str, float]:
    """Return ``(stance, confidence 0–1)`` for the market direction of an item.

    Confidence is the margin between the two vocabularies over their total, so a
    piece that is purely restrictive scores 1.0 and one that is evenly balanced —
    "imposes tariffs but grants exemptions" — lands near 0 and is reported as a
    plain mention rather than a direction the reader should trust.
    """
    if not text:
        return MENTIONED, 0.0
    neg = len({m.group(1).lower() for m in _RESTRICTIVE_RE.finditer(text)})
    pos = len({m.group(1).lower() for m in _SUPPORTIVE_RE.finditer(text)})
    if neg == 0 and pos == 0:
        return MENTIONED, 0.0
    margin = abs(neg - pos) / (neg + pos)
    if margin < 0.34:
        return MENTIONED, round(margin, 3)
    return (RESTRICTIVE if neg > pos else SUPPORTIVE), round(margin, 3)


def tickers_for_sectors(keys: list[str] | tuple[str, ...]) -> list[str]:
    """Watchlist tickers sitting in the given sectors, de-duplicated."""
    seen: list[str] = []
    for k in keys:
        for t in SECTORS[k].tickers if k in SECTORS else ():
            if t not in seen:
                seen.append(t)
    return seen
