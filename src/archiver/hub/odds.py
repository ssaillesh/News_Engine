"""Prediction-market odds on macro and policy questions, from Polymarket.

Each Polymarket event (say "Fed decision in December?") holds several yes/no
markets. The useful ones are open, still uncertain (a 99% market says nothing)
and actively traded, so those are kept and ranked by the last day's volume.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

# Polymarket tags that carry questions markets trade on.
ODDS_TAGS = ("economy", "fed-rates", "tariffs")
MIN_P, MAX_P = 0.03, 0.97


def _yes_price(market: dict[str, Any]) -> float | None:
    raw = market.get("outcomePrices")
    try:
        prices = json.loads(raw) if isinstance(raw, str) else raw
        return float(prices[0])
    except (TypeError, ValueError, IndexError, KeyError):
        return None


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def pick_odds(events: Iterable[dict[str, Any]], *, limit: int = 6) -> list[dict[str, Any]]:
    """The busiest open, undecided markets across ``events``, one row each."""
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for event in events:
        for market in event.get("markets") or []:
            key = str(market.get("id") or market.get("slug") or market.get("question"))
            if key in seen or market.get("closed") or market.get("active") is False:
                continue
            seen.add(key)
            p = _yes_price(market)
            if p is None or not MIN_P < p < MAX_P:
                continue
            change = _float(market.get("oneDayPriceChange"))
            slug = event.get("slug")
            rows.append(
                {
                    "question": market.get("question") or event.get("title") or "",
                    "probability": round(p * 100, 1),
                    "change_1d": round(change * 100, 1) if change is not None else None,
                    "volume_24h": _float(market.get("volume24hr")) or 0.0,
                    "url": f"https://polymarket.com/event/{slug}" if slug else None,
                }
            )
    rows.sort(key=lambda r: r["volume_24h"], reverse=True)
    return rows[:limit]
