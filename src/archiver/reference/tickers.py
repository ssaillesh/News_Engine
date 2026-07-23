"""Curated ticker dictionary + a disambiguating matcher.

Why curated rather than "scan for any capitalized word": naive substring or even
token matching produces almost entirely false positives on this corpus — "Intel"
matches *Artificial Intelligence*, "Ford" matches *Affordable*, "Delta" matches
the *Delta variant*. So this is a hand-picked list of large, publicly-traded
companies a US president plausibly names, each with vetted aliases, matched under
strict non-letter boundaries.

Two matching rules keep precision high:

* **Non-letter boundaries.** ``(?<![A-Za-z])alias(?![A-Za-z])`` — so ``Intel``
  never fires inside ``Intelligence`` and ``Ford`` never inside ``Affordable``.
* **No bare risky tokens.** Single ambiguous strings ("X", "T", "GE", bare
  "Delta") are omitted; a company is matched by a distinctive alias or not at all.
  A missed mention is recoverable on the next model pass; a wrong one is noise in
  a section whose whole value is trust.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Company:
    ticker: str
    name: str
    # Distinctive strings that denote this company. Matched case-insensitively
    # under non-letter boundaries; keep every entry unambiguous on its own.
    aliases: tuple[str, ...] = field(default_factory=tuple)


# ── the watchlist universe ────────────────────────────────────────────────────
# Ordered only for readability; matching order is handled by the compiler below.
_COMPANIES: tuple[Company, ...] = (
    Company("AAPL", "Apple", ("Apple",)),
    Company("AMZN", "Amazon", ("Amazon",)),
    Company("META", "Meta Platforms", ("Meta Platforms", "Facebook")),
    Company("GOOGL", "Alphabet (Google)", ("Google", "Alphabet")),
    Company("MSFT", "Microsoft", ("Microsoft",)),
    Company("NVDA", "Nvidia", ("Nvidia",)),
    Company("TSLA", "Tesla", ("Tesla",)),
    Company("F", "Ford Motor", ("Ford Motor", "Ford")),
    Company("GM", "General Motors", ("General Motors",)),
    Company("BA", "Boeing", ("Boeing",)),
    Company("INTC", "Intel", ("Intel",)),
    Company("WMT", "Walmart", ("Walmart", "Wal-Mart")),
    Company("KO", "Coca-Cola", ("Coca-Cola", "Coca Cola")),
    Company("HOG", "Harley-Davidson", ("Harley-Davidson", "Harley Davidson")),
    Company("GT", "Goodyear", ("Goodyear",)),
    Company("NKE", "Nike", ("Nike",)),
    Company("DIS", "Disney", ("Disney",)),
    Company("JPM", "JPMorgan Chase", ("JPMorgan", "JP Morgan")),
    Company("GS", "Goldman Sachs", ("Goldman Sachs",)),
    Company("XOM", "ExxonMobil", ("ExxonMobil", "Exxon Mobil", "Exxon")),
    Company("CVX", "Chevron", ("Chevron",)),
    Company("PFE", "Pfizer", ("Pfizer",)),
    Company("LLY", "Eli Lilly", ("Eli Lilly",)),
    Company("MRNA", "Moderna", ("Moderna",)),
    Company("UNH", "UnitedHealth", ("UnitedHealth",)),
    Company("LMT", "Lockheed Martin", ("Lockheed Martin", "Lockheed")),
    Company("CAT", "Caterpillar", ("Caterpillar",)),
    Company("DE", "Deere", ("John Deere", "Deere & Company")),
    Company("IBM", "IBM", ("IBM",)),
    Company("ORCL", "Oracle", ("Oracle",)),
    Company("PLTR", "Palantir", ("Palantir",)),
    Company("MU", "Micron", ("Micron",)),
    Company("WFC", "Wells Fargo", ("Wells Fargo",)),
    Company("BAC", "Bank of America", ("Bank of America",)),
    Company("VZ", "Verizon", ("Verizon",)),
    Company("MCD", "McDonald's", ("McDonald's", "McDonalds")),
    Company("SBUX", "Starbucks", ("Starbucks",)),
    Company("PEP", "PepsiCo", ("PepsiCo", "Pepsi")),
    Company("HD", "Home Depot", ("Home Depot",)),
    Company("COST", "Costco", ("Costco",)),
    Company("UAL", "United Airlines", ("United Airlines",)),
    Company("AAL", "American Airlines", ("American Airlines",)),
    Company("DAL", "Delta Air Lines", ("Delta Air Lines", "Delta Airlines")),
    Company("DJT", "Trump Media & Technology Group", ("Trump Media", "Truth Social")),
)

TICKERS: dict[str, Company] = {c.ticker: c for c in _COMPANIES}

# alias(lower) → ticker, longest alias first so "Exxon Mobil" wins over "Exxon".
_ALIAS_TO_TICKER: dict[str, str] = {}
for _c in _COMPANIES:
    for _alias in _c.aliases:
        _ALIAS_TO_TICKER[_alias.lower()] = _c.ticker

_SORTED_ALIASES = sorted(_ALIAS_TO_TICKER, key=len, reverse=True)

# One alternation, boundaries that reject an adjacent ASCII letter (but allow
# digits/punctuation, so "AT&T" or "3M"-style aliases would still work).
_MATCHER = re.compile(
    r"(?<![A-Za-z])(" + "|".join(re.escape(a) for a in _SORTED_ALIASES) + r")(?![A-Za-z])",
    re.IGNORECASE,
)


def find_tickers(text: str) -> dict[str, str]:
    """Return ``{ticker: first alias that matched}`` for companies named in text.

    One entry per company even if named several times; the alias is kept for
    display ("mentioned as 'Truth Social'") and for auditing false positives.
    """
    if not text:
        return {}
    found: dict[str, str] = {}
    for match in _MATCHER.finditer(text):
        alias = match.group(1)
        ticker = _ALIAS_TO_TICKER[alias.lower()]
        found.setdefault(ticker, alias)
    return found
