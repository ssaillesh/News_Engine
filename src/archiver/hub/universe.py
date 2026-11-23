"""The stock universe: every US-listed stock and ETF, plus a "core" set with prices.

* ``sync_universe`` loads every US symbol from Finnhub (one call) so search and
  browsing cover the whole market, and marks the core set: the S&P 500 (with
  GICS sectors, from the open ``datasets/s-and-p-500-companies`` list), large
  Nasdaq names outside it, and the major ETFs.
* ``backfill_core_prices`` fills 5 years of daily bars for core symbols from
  Yahoo, a batch at a time so a scheduled job stays short. Resumable.
* ``sync_core_eod`` keeps core prices current from Polygon/Massive's grouped
  daily endpoint: one call returns every US stock's bar for a day.

Non-core symbols are still fully usable: opening one fetches it on demand.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import TYPE_CHECKING, Any

import httpx
from loguru import logger
from sqlalchemy import func, select, update

from archiver.clients.exceptions import ClientError
from archiver.hub.service import HubReport, _upsert_rows, refresh_prices
from archiver.storage.models import PriceBar, Security, utcnow
from archiver.storage.repositories import _insert_for

if TYPE_CHECKING:
    from archiver.clients.market import FinnhubClient, PolygonClient, YahooChartClient
    from archiver.storage.db import Database

SP500_CSV = (
    "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
)

# Large Nasdaq-listed companies that are not in the S&P 500 (foreign filers and
# recent listings). Overlap with the S&P list is harmless: tags are merged.
LARGE_NASDAQ = [
    "ASML",
    "AZN",
    "ARM",
    "PDD",
    "MELI",
    "SHOP",
    "TEAM",
    "DDOG",
    "ZS",
    "MDB",
    "CCEP",
    "GFS",
    "MRVL",
    "BIDU",
    "JD",
    "NTES",
    "TCOM",
    "ALAB",
    "HOOD",
    "RKLB",
    "SOFI",
    "RIVN",
    "LCID",
    "NBIS",
    "CRWV",
]

# Broad market, size, style, bond, commodity, sector and theme ETFs.
MAJOR_ETFS = [
    "SPY",
    "VOO",
    "IVV",
    "VTI",
    "QQQ",
    "QQQM",
    "IWM",
    "DIA",
    "RSP",
    "VEA",
    "VWO",
    "EFA",
    "EEM",
    "VXUS",
    "AGG",
    "BND",
    "TLT",
    "IEF",
    "SHY",
    "LQD",
    "HYG",
    "TIP",
    "GLD",
    "SLV",
    "USO",
    "UNG",
    "XLK",
    "XLF",
    "XLE",
    "XLV",
    "XLY",
    "XLP",
    "XLI",
    "XLU",
    "XLB",
    "XLRE",
    "XLC",
    "SMH",
    "SOXX",
    "ARKK",
    "VNQ",
    "SCHD",
    "VIG",
    "VYM",
    "VUG",
    "VTV",
    "TQQQ",
    "SQQQ",
    "GDX",
    "KRE",
    "XBI",
    "IBIT",
    "ETHA",
]

# Finnhub symbol types worth listing, and the exchanges that count as "listed"
# (everything except OTC).
LISTED_TYPES = {"Common Stock", "ETP", "ADR", "REIT"}
OTC_MICS = {"OOTC", "OTCM", "PINX"}


@dataclass
class UniverseReport:
    symbols: int = 0
    core: int = 0
    sp500: int = 0
    days: list[str] = field(default_factory=list)
    bars: int = 0
    backfilled: int = 0
    errors: dict[str, str] = field(default_factory=dict)


async def fetch_sp500(client: httpx.AsyncClient | None = None) -> dict[str, dict[str, str]]:
    """S&P 500 constituents -> {ticker: {"name", "sector"}}. Empty on failure."""
    own = client is None
    client = client or httpx.AsyncClient(timeout=20, follow_redirects=True)
    try:
        resp = await client.get(SP500_CSV)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("S&P 500 list unavailable: {}", exc)
        return {}
    finally:
        if own:
            await client.aclose()
    out = {}
    for row in csv.DictReader(io.StringIO(resp.text)):
        ticker = (row.get("Symbol") or "").strip().upper()
        if ticker:
            out[ticker] = {
                "name": row.get("Security") or "",
                "sector": row.get("GICS Sector") or "",
            }
    return out


def core_tags(sp500: dict[str, dict[str, str]]) -> dict[str, list[str]]:
    tags: dict[str, list[str]] = {}
    for ticker in sp500:
        tags.setdefault(ticker, []).append("SP500")
    for ticker in LARGE_NASDAQ:
        tags.setdefault(ticker, []).append("NASDAQ_LARGE")
    for ticker in MAJOR_ETFS:
        tags.setdefault(ticker, []).append("ETF")
    return tags


def listed_rows(symbols: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Finnhub symbol rows -> {ticker: row} for exchange-listed stocks/ETFs."""
    out = {}
    for row in symbols:
        ticker = (row.get("symbol") or "").upper()
        if not ticker or row.get("type") not in LISTED_TYPES or row.get("mic") in OTC_MICS:
            continue
        out[ticker] = {
            "name": (row.get("description") or "").title() or None,
            "security_type": row.get("type"),
            "exchange": row.get("mic"),
            "currency": row.get("currency"),
        }
    return out


async def sync_universe(
    db: Database,
    finnhub: FinnhubClient,
    *,
    sp500: dict[str, dict[str, str]] | None = None,
) -> UniverseReport:
    """Load every listed US symbol and (re)mark the core set. Idempotent."""
    report = UniverseReport()
    if sp500 is None:
        sp500 = await fetch_sp500()
    report.sp500 = len(sp500)
    try:
        listed = listed_rows(await finnhub.symbols("US"))
    except ClientError as exc:
        report.errors["symbols"] = str(exc)
        listed = {}

    tags = core_tags(sp500)
    tickers = set(listed) | set(tags)
    now = utcnow()
    rows = []
    for ticker in sorted(tickers):
        base = listed.get(ticker, {})
        meta = sp500.get(ticker, {})
        rows.append(
            {
                "ticker": ticker,
                "name": meta.get("name") or base.get("name"),
                "security_type": base.get("security_type")
                or ("ETP" if ticker in MAJOR_ETFS else "Common Stock"),
                "exchange": base.get("exchange"),
                "currency": base.get("currency"),
                "sector": meta.get("sector") or ("ETF" if ticker in MAJOR_ETFS else None),
                "tags": tags.get(ticker),
                "is_core": ticker in tags,
                "refreshed_at": now,
            }
        )

    table = Security.__table__
    insert = _insert_for(db.dialect)
    async with db.session() as session, session.begin():
        for start in range(0, len(rows), 500):
            stmt = insert(table).values(rows[start : start + 500])
            ex = stmt.excluded
            await session.execute(
                stmt.on_conflict_do_update(
                    index_elements=["ticker"],
                    set_={
                        # Profile data from Finnhub (fuller names) wins when present.
                        "name": func.coalesce(table.c.name, ex.name),
                        "exchange": func.coalesce(table.c.exchange, ex.exchange),
                        "currency": func.coalesce(table.c.currency, ex.currency),
                        "security_type": ex.security_type,
                        "sector": func.coalesce(ex.sector, table.c.sector),
                        "tags": ex.tags,
                        "is_core": ex.is_core,
                    },
                )
            )
        # Only demote symbols when the S&P list actually loaded; a network blip
        # must not strip the core flag from 500 stocks.
        if sp500:
            await session.execute(
                update(Security)
                .where(Security.is_core.is_(True), Security.ticker.not_in(list(tags)))
                .values(is_core=False, tags=None)
            )
    report.symbols = len(rows)
    report.core = len(tags)
    return report


async def core_tickers(db: Database) -> list[str]:
    async with db.session() as session:
        rows = await session.scalars(select(Security.ticker).where(Security.is_core.is_(True)))
        return sorted(rows.all())


async def backfill_core_prices(
    db: Database, yahoo: YahooChartClient, *, limit: int = 100, min_bars: int = 200
) -> UniverseReport:
    """5-year history for core symbols that don't have it yet, ``limit`` per run."""
    report = UniverseReport()
    counts = select(PriceBar.ticker, func.count().label("n")).group_by(PriceBar.ticker).subquery()
    async with db.session() as session:
        todo = (
            await session.scalars(
                select(Security.ticker)
                .outerjoin(counts, counts.c.ticker == Security.ticker)
                .where(Security.is_core.is_(True), func.coalesce(counts.c.n, 0) < min_bars)
                .order_by(Security.ticker)
                .limit(limit)
            )
        ).all()
    hub = HubReport()
    for ticker in todo:
        await refresh_prices(db, yahoo, ticker, report=hub)
        report.backfilled += 1
    report.bars = hub.bars
    report.errors.update(hub.errors)
    return report


def _trading_days(start: date, end: date) -> list[date]:
    days, day = [], start
    while day <= end:
        if day.weekday() < 5:  # holidays simply come back empty
            days.append(day)
        day += timedelta(days=1)
    return days


async def sync_core_eod(
    db: Database, polygon: PolygonClient, *, max_days: int = 10, today: date | None = None
) -> UniverseReport:
    """Write end-of-day bars for core symbols for each day since the last one stored."""
    report = UniverseReport()
    core = set(await core_tickers(db))
    if not core:
        return report
    today = today or datetime.now(UTC).date()
    async with db.session() as session:
        last = await session.scalar(
            select(func.max(PriceBar.date)).where(PriceBar.ticker.in_(list(core)))
        )
    start = (last + timedelta(days=1)) if last else today - timedelta(days=7)
    # The free plan serves end-of-day data, so stop at yesterday.
    for day in _trading_days(start, today - timedelta(days=1))[:max_days]:
        try:
            bars = await polygon.grouped_daily(day)
        except ClientError as exc:
            report.errors[day.isoformat()] = str(exc)
            break  # later days depend on the same quota; retry next run
        rows = [
            {
                "ticker": t,
                "date": b.date,
                "open": b.open,
                "high": b.high,
                "low": b.low,
                "close": b.close,
                "adj_close": b.adj_close,
                "volume": b.volume,
            }
            for t, b in bars.items()
            if t in core
        ]
        if rows:
            await _upsert_rows(db, PriceBar.__table__, rows, ["ticker", "date"])
            report.days.append(day.isoformat())
            report.bars += len(rows)
    await update_core_quotes(db)
    return report


async def update_core_quotes(db: Database) -> int:
    """Set price/change on core securities from their last two daily bars.

    Never overwrites a newer live quote (tracked tickers get those from Finnhub).
    """
    async with db.session() as session:
        latest = await session.scalar(select(func.max(PriceBar.date)))
        if latest is None:
            return 0
        rows = (
            await session.execute(
                select(PriceBar.ticker, PriceBar.date, PriceBar.close)
                .join(Security, Security.ticker == PriceBar.ticker)
                .where(Security.is_core.is_(True), PriceBar.date >= latest - timedelta(days=10))
                .order_by(PriceBar.ticker, PriceBar.date.desc())
            )
        ).all()
        quoted = dict(
            (
                await session.execute(
                    select(Security.ticker, Security.quote_at).where(Security.is_core.is_(True))
                )
            ).all()
        )
    by_ticker: dict[str, list[tuple[date, float]]] = {}
    for ticker, day, close in rows:
        if close is not None and len(by_ticker.setdefault(ticker, [])) < 2:
            by_ticker[ticker].append((day, close))

    updates = []
    for ticker, bars in by_ticker.items():
        day, close = bars[0]
        stamp = datetime.combine(day, time(21, 0), UTC)  # after the US close
        current = quoted.get(ticker)
        if (
            current is not None
            and (current if current.tzinfo else current.replace(tzinfo=UTC)) >= stamp
        ):
            continue
        prev = bars[1][1] if len(bars) > 1 else None
        change = close - prev if prev else None
        updates.append(
            {
                "ticker": ticker,
                "price": close,
                "prev_close": prev,
                "change": change,
                "pct_change": (change / prev * 100) if prev and change is not None else None,
                "quote_at": stamp,
            }
        )
    if updates:
        async with db.session() as session, session.begin():
            await session.execute(update(Security), updates)
    return len(updates)
