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
    *,
    base: str | None = None,
    fx: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Roll lots up into positions valued at the latest quote.

    ``quotes`` maps ticker to a dict with ``price``, ``change`` and optionally
    ``name`` and ``currency``. A position with no price yet is still listed but
    left out of the totals, and flagged, rather than silently valued at zero.

    Each position is reported in its own currency (what the exchange quotes and
    what its average cost was entered in). With ``base`` set, totals and weights
    are in ``base``: every other currency is converted at ``fx[ccy]`` (units of
    ``base`` per one ``ccy``), cost included, so a position's P&L in ``base`` is
    its P&L in its own currency at today's rate and leaves out currency moves
    since purchase. A currency with no rate is never guessed: its positions are
    listed in ``unconverted`` and kept out of the totals.
    """
    rates = dict(fx or {})

    def rate(ccy: str) -> float | None:
        return 1.0 if base is None or ccy == base else rates.get(ccy)

    grouped: dict[str, list[Lot]] = {}
    for lot in lots:
        grouped.setdefault(lot.ticker.upper(), []).append(lot)

    positions: list[dict[str, Any]] = []
    total_value = total_cost = day_change = 0.0
    priced_cost = 0.0
    unpriced: list[str] = []
    unconverted: list[str] = []
    used: dict[str, float] = {}

    for ticker, ticker_lots in sorted(grouped.items()):
        shares = sum(lot.shares for lot in ticker_lots)
        cost = sum(lot.shares * lot.avg_cost for lot in ticker_lots)
        quote = quotes.get(ticker) or {}
        price = quote.get("price")
        change = quote.get("change")
        ccy = str(quote.get("currency") or base or "USD").upper()
        r = rate(ccy)
        if r is None:
            unconverted.append(ticker)
        elif ccy != base and base is not None:
            used[ccy] = r

        value = pnl = pnl_pct = day = None
        if price is not None:
            value = shares * price
            pnl = value - cost
            pnl_pct = (pnl / cost * 100) if cost else None
            day = shares * change if change is not None else None
        else:
            unpriced.append(ticker)

        if r is not None:
            total_cost += cost * r
            if value is not None:
                total_value += value * r
                priced_cost += cost * r
                day_change += (day or 0.0) * r

        positions.append(
            {
                "ticker": ticker,
                "name": quote.get("name"),
                "currency": ccy,
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
                # The same figures in the portfolio's base currency.
                "market_value_base": _round(value * r) if value is not None and r else None,
                "unrealized_pnl_base": _round(pnl * r) if pnl is not None and r else None,
                "day_change_base": _round(day * r) if day is not None and r else None,
            }
        )

    for position in positions:
        value = position["market_value_base"]
        position["weight_pct"] = (
            _round(value / total_value * 100) if value is not None and total_value else None
        )

    total_pnl = total_value - priced_cost
    prev_value = total_value - day_change
    return {
        "positions": sorted(positions, key=lambda p: p["market_value_base"] or 0, reverse=True),
        "totals": {
            "currency": base,
            "market_value": _round(total_value),
            "cost_basis": _round(total_cost),
            "unrealized_pnl": _round(total_pnl),
            "unrealized_pnl_pct": _round(total_pnl / priced_cost * 100) if priced_cost else None,
            "day_change": _round(day_change),
            "day_change_pct": _round(day_change / prev_value * 100) if prev_value else None,
        },
        "fx": {ccy: round(v, 6) for ccy, v in sorted(used.items())},
        "unpriced": unpriced,
        "unconverted": unconverted,
    }
