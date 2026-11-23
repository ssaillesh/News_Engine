"""Live quotes while ``archiver serve`` runs.

Stored data only moves when a batch job runs, so during the trading day every
price on the hub would otherwise sit at the last close. Each minute this loop
refreshes the quotes on ``securities``:

* the *priority* set (the index, sector and cross-asset ETFs the pages chart,
  the watchlist and holdings, and companies in the last two days of news) from
  Finnhub's real-time ``/quote``, which also carries the day's open/high/low;
* everything else in the core universe from Yahoo's batch spark endpoint,
  twenty symbols a call, so the screener and movers never mix today's moves
  with an older session's.

Outside regular hours it does one last pass after the close and then idles.
Finnhub's free plan allows 60 calls a minute; the default budget leaves room
for on-demand ticker refreshes from the pages.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from datetime import UTC, date, datetime, time, timedelta
from typing import TYPE_CHECKING

from loguru import logger
from sqlalchemy import select, update

from archiver.clients.exceptions import ClientError
from archiver.hub.returns import ET
from archiver.storage.models import Holding, Security, Status, StockMention, WatchlistItem

if TYPE_CHECKING:
    from archiver.clients.market import FinnhubClient, Quote, YahooChartClient
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


async def core_universe(db: Database) -> list[str]:
    async with db.session() as session:
        rows = await session.scalars(
            select(Security.ticker).where(Security.is_core.is_(True)).order_by(Security.ticker)
        )
        return list(rows.all())


def _day(at: datetime | None) -> date | None:
    return (at if at.tzinfo else at.replace(tzinfo=UTC)).astimezone(ET).date() if at else None


async def write_quotes(db: Database, quotes: dict[str, Quote]) -> int:
    """Store quotes on existing ``securities`` rows; returns how many were written.

    A quote older than the stored one is skipped. One without a day range (Yahoo)
    keeps the stored range only if it is from the same session, so a stale
    high/low never sits beside today's price.
    """
    if not quotes:
        return 0
    async with db.session() as session, session.begin():
        stored = dict(
            (
                await session.execute(
                    select(Security.ticker, Security.quote_at).where(
                        Security.ticker.in_(list(quotes))
                    )
                )
            ).all()
        )
        # Two executemany batches (with and without a day range), keyed by
        # primary key: one round trip each instead of one per ticker on Neon.
        full: list[dict[str, object]] = []
        bare: list[dict[str, object]] = []
        for t, q in quotes.items():
            if t not in stored or q.price is None:
                continue
            at = q.at or datetime.now(UTC)
            old = stored[t]
            if old is not None and (old if old.tzinfo else old.replace(tzinfo=UTC)) > at:
                continue
            values: dict[str, object] = {
                "ticker": t,
                "price": q.price,
                "change": q.change,
                "pct_change": q.pct_change,
                "prev_close": q.prev_close,
                "quote_at": at,
            }
            if q.day_high is not None or _day(old) != _day(at):
                values.update(day_open=q.day_open, day_high=q.day_high, day_low=q.day_low)
                full.append(values)
            else:
                bare.append(values)
        for batch in (full, bare):
            if batch:
                await session.execute(update(Security), batch)
        n = len(full) + len(bare)
    return n


async def finnhub_quotes(finnhub: FinnhubClient, tickers: Iterable[str]) -> dict[str, Quote]:
    out: dict[str, Quote] = {}
    for t in tickers:
        try:
            out[t] = await finnhub.quote(t)
        except ClientError as exc:
            logger.debug("live quote {} failed: {}", t, exc)
    return out


async def spark_quotes(yahoo: YahooChartClient, tickers: list[str]) -> dict[str, Quote]:
    from archiver.clients.market import SPARK_BATCH

    out: dict[str, Quote] = {}
    for i in range(0, len(tickers), SPARK_BATCH):
        try:
            out.update(await yahoo.spark(tickers[i : i + SPARK_BATCH]))
        except ClientError as exc:
            logger.debug("spark batch {} failed: {}", i // SPARK_BATCH, exc)
    return out


async def refresh_quotes(db: Database, finnhub: FinnhubClient, tickers: Iterable[str]) -> int:
    """Finnhub quotes for ``tickers``, written; a failed symbol is skipped."""
    return await write_quotes(db, await finnhub_quotes(finnhub, tickers))


async def live_quote_loop(db: Database, settings: Settings, *, budget: int = 40) -> None:
    """Run until cancelled. ``budget`` is Finnhub calls per cycle (one cycle a minute)."""
    from archiver.clients.market import FinnhubClient, YahooChartClient
    from archiver.clients.rate_limit import TokenBucket

    # A slower bucket than the shared default, so on-demand page refreshes
    # (their own client, same key) still fit inside Finnhub's 60/min.
    rps = min(settings.finnhub_rps, budget / CYCLE_S + 0.05)
    closed_pass_done = False
    logger.info("live quotes: on (Finnhub {} calls/min + Yahoo batch)", budget)
    while True:
        started = asyncio.get_running_loop().time()
        is_open = market_open()
        try:
            if is_open or not closed_pass_done:
                fast = plan(await priority_tickers(db), [], budget)
                bulk = [t for t in await core_universe(db) if t not in set(fast)]
                async with (
                    FinnhubClient.from_settings(settings, rate_limiter=TokenBucket(rps)) as fh,
                    YahooChartClient.from_settings(settings) as yahoo,
                ):
                    a, b = await asyncio.gather(finnhub_quotes(fh, fast), spark_quotes(yahoo, bulk))
                n = await write_quotes(db, {**b, **a})
                logger.debug("live quotes: {} written ({} finnhub, {} yahoo)", n, len(a), len(b))
                closed_pass_done = not is_open
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # never let a bad cycle kill the loop
            logger.warning("live quotes cycle failed: {}", exc)
        wait = CYCLE_S if is_open else 300.0
        elapsed = asyncio.get_running_loop().time() - started
        await asyncio.sleep(max(5.0, wait - elapsed))
