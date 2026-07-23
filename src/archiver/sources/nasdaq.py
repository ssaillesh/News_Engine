"""Nasdaq market data — live quotes and the earnings calendar.

Nasdaq's public JSON API (``api.nasdaq.com``) serves both a per-symbol quote and a
per-date earnings calendar with no API key. It does reject the default client
user-agent, so this client sends a browser-like one.

The refresh here reads the Trump watchlist (distinct tickers in ``stock_mentions``)
and, for each, caches a quote plus its next scheduled quarterly report into
``company_market``. The dashboard then reads only that cache and never blocks on
Nasdaq. Quotes are best-effort: one symbol failing records a ``quote_error`` on
that row and the others still refresh.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any

from loguru import logger
from sqlalchemy import select

from archiver.clients.base import BaseHttpClient
from archiver.clients.exceptions import ClientError
from archiver.clients.rate_limit import RateLimiter, TokenBucket
from archiver.reference.tickers import TICKERS
from archiver.storage.models import StockMention
from archiver.storage.repositories import CompanyMarketRepository

if TYPE_CHECKING:
    from archiver.config.settings import Settings
    from archiver.storage.db import Database

# Nasdaq blocks non-browser agents on this host; this UA is for access, not
# disguise — the requests are ordinary public-API GETs.
_BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) trump-news-archiver/0.1"

# How far ahead to scan the earnings calendar for watchlist report dates.
DEFAULT_EARNINGS_HORIZON_DAYS = 75


class NasdaqClient(BaseHttpClient):
    BASE_URL = "https://api.nasdaq.com"

    @classmethod
    def from_settings(
        cls, settings: Settings, *, rate_limiter: RateLimiter | None = None
    ) -> NasdaqClient:
        return cls(
            cls.BASE_URL,
            user_agent=_BROWSER_UA,
            timeout_s=settings.http_timeout_s,
            max_retries=settings.http_max_retries,
            backoff_base_s=settings.backoff_base_s,
            backoff_cap_s=settings.backoff_cap_s,
            rate_limiter=rate_limiter or TokenBucket(settings.rate_limit_rps),
        )

    async def fetch_quote(self, ticker: str) -> dict[str, Any]:
        """Return the ``data`` block of a symbol's quote (raises on API error)."""
        result = await self.get_json(
            f"/api/quote/{ticker}/info", params={"assetclass": "stocks"}
        )
        body = result.data if isinstance(result.data, dict) else {}
        payload = body.get("data")
        if not isinstance(payload, dict):
            raise ClientError(f"no quote data for {ticker} (message: {body.get('message')})")
        return payload

    async def fetch_earnings(self, day: date) -> list[dict[str, Any]]:
        """Return the earnings-calendar rows for a single date (empty if none)."""
        result = await self.get_json(
            "/api/calendar/earnings", params={"date": day.isoformat()}
        )
        body = result.data if isinstance(result.data, dict) else {}
        block = body.get("data")
        if not isinstance(block, dict):
            return []
        return block.get("rows") or []


def _quote_fields(payload: dict[str, Any]) -> dict[str, Any]:
    primary = payload.get("primaryData") or {}
    return {
        "last_price": primary.get("lastSalePrice"),
        "net_change": primary.get("netChange"),
        "pct_change": primary.get("percentageChange"),
        "delta_indicator": primary.get("deltaIndicator"),
        "price_as_of": primary.get("lastTradeTimestamp"),
    }


async def _watchlist(db: Database) -> list[str]:
    """Distinct tickers Trump has mentioned, i.e. the watchlist."""
    async with db.session() as session:
        rows = (await session.scalars(select(StockMention.ticker).distinct())).all()
    return sorted(rows)


async def _earnings_map(
    client: NasdaqClient, watchlist: set[str], horizon_days: int
) -> dict[str, dict[str, Any]]:
    """Earliest upcoming report per watchlist ticker, scanning day by day.

    Stops early once every watchlist company has a date, so a small watchlist
    costs only a few requests even with a long horizon.
    """
    found: dict[str, dict[str, Any]] = {}
    today = datetime.now(UTC).date()
    for offset in range(horizon_days + 1):
        if len(found) >= len(watchlist):
            break
        day = today + timedelta(days=offset)
        if day.weekday() >= 5:  # earnings are reported on weekdays
            continue
        try:
            rows = await client.fetch_earnings(day)
        except ClientError as exc:
            logger.warning("earnings calendar failed for {}: {}", day, exc)
            continue
        for row in rows:
            symbol = (row.get("symbol") or "").upper()
            if symbol in watchlist and symbol not in found:
                found[symbol] = {
                    "next_earnings_date": day.isoformat(),
                    "next_earnings_eps_forecast": row.get("epsForecast"),
                    "next_earnings_time": row.get("time"),
                    "market_cap": row.get("marketCap"),
                }
    return found


async def refresh_market(
    db: Database,
    *,
    settings: Settings,
    horizon_days: int = DEFAULT_EARNINGS_HORIZON_DAYS,
    tickers: Sequence[str] | None = None,
    rate_limiter: RateLimiter | None = None,
) -> int:
    """Refresh cached quote + next-earnings data for the watchlist.

    ``tickers`` overrides the watchlist (mainly for tests). Returns how many
    company rows were written.
    """
    watchlist = list(tickers) if tickers is not None else await _watchlist(db)
    if not watchlist:
        return 0

    async with NasdaqClient.from_settings(settings, rate_limiter=rate_limiter) as client:
        earnings = await _earnings_map(client, set(watchlist), horizon_days)

        written = 0
        for ticker in watchlist:
            company = TICKERS.get(ticker)
            row: dict[str, Any] = {
                "ticker": ticker,
                "name": company.name if company else ticker,
                "quote_error": None,
                **earnings.get(ticker, {}),
            }
            try:
                row.update(_quote_fields(await client.fetch_quote(ticker)))
            except ClientError as exc:
                row["quote_error"] = str(exc)
                logger.warning("quote failed for {}: {}", ticker, exc)

            async with db.session() as session, session.begin():
                await CompanyMarketRepository(session, db.dialect).upsert(row)
            written += 1
    return written
