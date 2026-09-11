"""Yahoo Finance fetcher (yfinance).

The only data source wired up so far. yfinance is an unofficial client: Yahoo
can change its responses without notice, so everything here is defensive and
every failure is raised as :class:`YahooError` for the caller to handle.

Prices come back with ``auto_adjust=False``, which yields Yahoo's split-adjusted
OHLC. Dividend adjustment is deliberately not applied — the ``prices`` schema
has one ``close`` column, and split-adjusted is the convention for charting.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import yfinance as yf


class YahooError(RuntimeError):
    """Raised when Yahoo returns nothing usable for a ticker."""


@dataclass(frozen=True, slots=True)
class PriceBar:
    """One daily OHLCV bar."""

    date: dt.date
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: int | None


@dataclass(frozen=True, slots=True)
class SecurityProfile:
    """Descriptive fields for a ticker, all optional but the symbol."""

    ticker: str
    name: str | None = None
    exchange: str | None = None
    sector: str | None = None
    market_cap: int | None = None


def _as_float(value: object) -> float | None:
    try:
        out = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return None if out != out else out  # drop NaN


def _as_int(value: object) -> int | None:
    out = _as_float(value)
    return None if out is None else int(out)


def fetch_profile(ticker: str) -> SecurityProfile:
    """Look up descriptive fields. Never raises — falls back to the bare symbol.

    ``.info`` is the flakiest part of yfinance, and a missing sector must not
    stop a price backfill.
    """
    symbol = ticker.upper()
    try:
        info = yf.Ticker(symbol).info or {}
    except Exception:
        return SecurityProfile(ticker=symbol)

    return SecurityProfile(
        ticker=symbol,
        name=info.get("longName") or info.get("shortName"),
        exchange=info.get("fullExchangeName") or info.get("exchange"),
        sector=info.get("sector"),
        market_cap=_as_int(info.get("marketCap")),
    )


def fetch_daily_prices(ticker: str, *, period: str = "max") -> list[PriceBar]:
    """Return daily bars, oldest first.

    :param period: any yfinance period — ``"max"``, ``"10y"``, ``"1mo"``.
    :raises YahooError: when the symbol is unknown or the download is empty.
    """
    symbol = ticker.upper()
    try:
        frame = yf.Ticker(symbol).history(period=period, interval="1d", auto_adjust=False)
    except Exception as exc:  # network, parsing, Yahoo shape changes
        raise YahooError(f"download failed for {symbol}: {exc}") from exc

    if frame is None or frame.empty:
        raise YahooError(f"no price data returned for {symbol}")

    bars: list[PriceBar] = []
    for stamp, row in frame.iterrows():
        bars.append(
            PriceBar(
                date=stamp.date(),
                open=_as_float(row.get("Open")),
                high=_as_float(row.get("High")),
                low=_as_float(row.get("Low")),
                close=_as_float(row.get("Close")),
                volume=_as_int(row.get("Volume")),
            )
        )
    return bars
