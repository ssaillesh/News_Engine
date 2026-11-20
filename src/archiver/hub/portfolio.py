"""Portfolio math. Pure: rows in, numbers out, no database or network."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Lot:
    ticker: str
    shares: float
    avg_cost: float


def _round(value: float | None, places: int = 2) -> float | None:
    return None if value is None else round(value, places)


def summarize(
    lots: Iterable[Lot],
    quotes: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Roll lots up into positions valued at the latest quote.

    ``quotes`` maps ticker to a dict with ``price``, ``change`` and optionally
    ``name``. A position with no price yet is still listed but left out of the
    totals, and flagged, rather than silently valued at zero.
    """
    grouped: dict[str, list[Lot]] = {}
    for lot in lots:
        grouped.setdefault(lot.ticker.upper(), []).append(lot)

    positions: list[dict[str, Any]] = []
    total_value = total_cost = day_change = 0.0
    priced_cost = 0.0
    unpriced: list[str] = []

    for ticker, ticker_lots in sorted(grouped.items()):
        shares = sum(lot.shares for lot in ticker_lots)
        cost = sum(lot.shares * lot.avg_cost for lot in ticker_lots)
        quote = quotes.get(ticker) or {}
        price = quote.get("price")
        change = quote.get("change")
        total_cost += cost

        value = pnl = pnl_pct = day = None
        if price is not None:
            value = shares * price
            pnl = value - cost
            pnl_pct = (pnl / cost * 100) if cost else None
            day = shares * change if change is not None else None
            total_value += value
            priced_cost += cost
            day_change += day or 0.0
        else:
            unpriced.append(ticker)

        positions.append(
            {
                "ticker": ticker,
                "name": quote.get("name"),
                "lots": len(ticker_lots),
                "shares": shares,
                "avg_cost": _round(cost / shares if shares else None, 4),
                "cost_basis": _round(cost),
                "price": price,
                "market_value": _round(value),
                "unrealized_pnl": _round(pnl),
                "unrealized_pnl_pct": _round(pnl_pct),
                "day_change": _round(day),
                "day_change_pct": quote.get("pct_change"),
            }
        )

    for position in positions:
        value = position["market_value"]
        position["weight_pct"] = (
            _round(value / total_value * 100) if value is not None and total_value else None
        )

    total_pnl = total_value - priced_cost
    prev_value = total_value - day_change
    return {
        "positions": sorted(positions, key=lambda p: p["market_value"] or 0, reverse=True),
        "totals": {
            "market_value": _round(total_value),
            "cost_basis": _round(total_cost),
            "unrealized_pnl": _round(total_pnl),
            "unrealized_pnl_pct": _round(total_pnl / priced_cost * 100) if priced_cost else None,
            "day_change": _round(day_change),
            "day_change_pct": _round(day_change / prev_value * 100) if prev_value else None,
        },
        "unpriced": unpriced,
    }
