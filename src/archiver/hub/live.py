"""Live quotes while ``archiver serve`` runs.

Stored data only moves when a batch job runs, so during the trading day every
price on the hub would otherwise sit at the last close. This loop keeps the
quotes on ``securities`` current from Finnhub's real-time ``/quote``:

* every cycle it refreshes the *priority* set (the index, sector and
  cross-asset ETFs the pages chart, the watchlist and holdings, and companies
  in the last two days of news), then
* spends what is left of the per-minute budget on the rest of the core
  universe, stalest first, so screener and movers catch up within minutes.

Outside regular hours it does one last pass after the close and then idles.
Finnhub's free plan allows 60 calls a minute; the default budget leaves room
for on-demand ticker refreshes from the pages.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from datetime import UTC, datetime, time, timedelta
from typing import TYPE_CHECKING

from loguru import logger
from sqlalchemy import select, update

from archiver.clients.exceptions import ClientError
from archiver.hub.returns import ET
from archiver.storage.models import Holding, Security, Status, StockMention, WatchlistItem

if TYPE_CHECKING:
    from archiver.clients.market import FinnhubClient
    from archiver.config.settings import Settings
    from archiver.storage.db import Database

# What the pages chart: indices, sector SPDRs, cross-asset proxies, the tape.
PRIORITY = (
    "SPY", "QQQ", "DIA", "IWM",
    "XLK", "XLC", "XLY", "XLF", "XLV", "XLI", "XLP", "XLE", "XLU", "XLRE", "XLB",
    "TLT", "GLD", "USO", "UUP", "IBIT", "SMH",
)  # fmt: skip
OPEN, CLOSE = time(9, 30), time(16, 0)
CYCLE_S = 60.0


def market_open(now: datetime | None = None) -> bool:
    """Regular US session, weekdays 9:30-16:00 ET (exchange holidays not modelled:
    on one, Finnhub just keeps returning the prior close)."""
    local = (now or datetime.now(UTC)).astimezone(ET)
    return local.weekday() < 5 and OPEN <= local.time() < CLOSE


def plan(priority: Iterable[str], rotation: Iterable[str], budget: int) -> list[str]:
    """Priority tickers first (deduplicated, in order), then rotation up to ``budget``."""
    out: list[str] = []
    seen: set[str] = set()
    for t in [*priority, *rotation]:
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
        if len(out) >= budget:
            break
    return out


async def priority_tickers(db: Database, *, news_hours: int = 48, news_cap: int = 25) -> list[str]:
    since = datetime.now(UTC) - timedelta(hours=news_hours)
    async with db.session() as session:
        watched = (await session.scalars(select(WatchlistItem.ticker))).all()
        held = (await session.scalars(select(Holding.ticker).distinct())).all()
        named = (
            await session.scalars(
                select(StockMention.ticker)
                .join(Status, Status.id == StockMention.status_id)
                .where(Status.created_at >= since)
                .group_by(StockMention.ticker)
                .order_by(StockMention.ticker)
                .limit(news_cap)
            )
        ).all()
        known = set(
            (
                await session.scalars(select(Security.ticker).where(Security.ticker.in_(PRIORITY)))
            ).all()
        )
    return [*(t for t in PRIORITY if t in known), *watched, *held, *named]


async def stalest_core(db: Database, limit: int) -> list[str]:
    async with db.session() as session:
        rows = await session.scalars(
            select(Security.ticker)
            .where(Security.is_core.is_(True))
            .order_by(Security.quote_at.asc().nulls_first(), Security.ticker)
            .limit(limit)
        )
        return list(rows.all())


async def refresh_quotes(db: Database, finnhub: FinnhubClient, tickers: Iterable[str]) -> int:
    """Write the latest quote for each ticker that has a ``securities`` row. Returns
    how many were updated; a failed symbol is skipped, not fatal."""
    rows = []
    for t in tickers:
        try:
            q = await finnhub.quote(t)
        except ClientError as exc:
            logger.debug("live quote {} failed: {}", t, exc)
            continue
        rows.append(
            {
                "ticker": t,
                "price": q.price,
                "change": q.change,
                "pct_change": q.pct_change,
                "day_open": q.day_open,
                "day_high": q.day_high,
                "day_low": q.day_low,
                "prev_close": q.prev_close,
                "quote_at": q.at or datetime.now(UTC),
            }
        )
    if rows:
        async with db.session() as session, session.begin():
            for r in rows:
                t = r.pop("ticker")
                await session.execute(update(Security).where(Security.ticker == t).values(**r))
    return len(rows)


async def live_quote_loop(db: Database, settings: Settings, *, budget: int = 40) -> None:
    """Run until cancelled. ``budget`` is Finnhub calls per cycle (one cycle a minute)."""
    from archiver.clients.market import FinnhubClient
    from archiver.clients.rate_limit import TokenBucket

    # A slower bucket than the shared default, so on-demand page refreshes
    # (their own client, same key) still fit inside Finnhub's 60/min.
    rps = min(settings.finnhub_rps, budget / CYCLE_S + 0.05)
    closed_pass_done = False
    logger.info("live quotes: on ({} calls/min)", budget)
    while True:
        started = asyncio.get_running_loop().time()
        is_open = market_open()
        try:
            if is_open or not closed_pass_done:
                prio = await priority_tickers(db)
                rest = await stalest_core(db, budget) if is_open else []
                todo = plan(prio, rest, budget)
                async with FinnhubClient.from_settings(
                    settings, rate_limiter=TokenBucket(rps)
                ) as finnhub:
                    n = await refresh_quotes(db, finnhub, todo)
                logger.debug("live quotes: {}/{} updated", n, len(todo))
                closed_pass_done = not is_open
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # never let a bad cycle kill the loop
            logger.warning("live quotes cycle failed: {}", exc)
        wait = CYCLE_S if is_open else 300.0
        elapsed = asyncio.get_running_loop().time() - started
        await asyncio.sleep(max(5.0, wait - elapsed))
