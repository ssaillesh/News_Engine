"""Investment hub data refresh: quotes, fundamentals, price history, company news.

Every function takes already-open clients so the CLI, the API and tests can each
supply their own (a mock transport in tests). Failures for one ticker are
recorded and skipped; one delisted symbol must never stop the whole refresh.

Company news is archived as ordinary statuses (``source="market_news"``) and
linked to tickers through ``stock_mentions``. That way FinBERT sentiment, impact
scoring, the feed and its filters all work on it with no extra code.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any

from loguru import logger
from sqlalchemy import func, select

from archiver.clients.exceptions import ClientError
from archiver.clients.market import is_foreign
from archiver.domain.hashing import content_hash
from archiver.storage.models import Holding, PriceBar, Security, WatchlistItem, utcnow
from archiver.storage.repositories import (
    AccountRepository,
    StatusRepository,
    StockMentionRepository,
    _insert_for,
)

if TYPE_CHECKING:
    from archiver.clients.market import FinnhubClient, YahooChartClient
    from archiver.storage.db import Database

NEWS_SOURCE = "market_news"
NEWS_ALIAS = "finnhub"  # stock_mentions.alias for provider-tagged links
NEWS_PER_TICKER = 50
MARKET_ACCOUNT: dict[str, Any] = {
    "id": "market:finnhub",
    "username": "MarketNews",
    "acct": "company-news@finnhub.io",
    "display_name": "Company news",
    "url": "https://finnhub.io/",
}
PROFILE_MAX_AGE = timedelta(days=7)

_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


def normalize_ticker(raw: str) -> str:
    ticker = (raw or "").strip().upper()
    if not _TICKER_RE.match(ticker):
        raise ValueError(f"not a valid ticker: {raw!r}")
    return ticker


@dataclass
class HubReport:
    tickers: int = 0
    quotes: int = 0
    bars: int = 0
    news: int = 0
    errors: dict[str, str] = field(default_factory=dict)

    def fail(self, ticker: str, step: str, exc: Exception) -> None:
        self.errors[f"{ticker}:{step}"] = str(exc)
        logger.warning("hub {} failed for {}: {}", step, ticker, exc)


async def tracked_tickers(db: Database) -> list[str]:
    """Everything the user follows: watchlist plus holdings."""
    async with db.session() as session:
        watched = (await session.scalars(select(WatchlistItem.ticker))).all()
        held = (await session.scalars(select(Holding.ticker).distinct())).all()
    return sorted({*watched, *held})


async def _upsert_rows(
    db: Database, table: Any, rows: list[dict[str, Any]], keys: list[str]
) -> None:
    """Multi-row upsert in chunks: one round trip per 500 rows, not per row.

    That matters on a remote database: 1,255 daily bars one statement at a time
    cost ~40s per ticker against Neon; batched it is well under a second.
    """
    if not rows:
        return
    columns = [c for c in rows[0] if c not in keys]
    async with db.session() as session, session.begin():
        for start in range(0, len(rows), 500):
            stmt = _insert_for(db.dialect)(table).values(rows[start : start + 500])
            update = {c: getattr(stmt.excluded, c) for c in columns}
            await session.execute(stmt.on_conflict_do_update(index_elements=keys, set_=update))


# ── quotes, profile, fundamentals ────────────────────────────────────────────
async def refresh_security(
    db: Database, finnhub: FinnhubClient, ticker: str, *, report: HubReport | None = None
) -> bool:
    """Refresh one ticker's quote (always), fundamentals and profile (when stale)."""
    report = report or HubReport()
    async with db.session() as session:
        existing = await session.get(Security, ticker)

    row: dict[str, Any] = {"ticker": ticker, "refreshed_at": utcnow(), "last_error": None}
    try:
        quote = await finnhub.quote(ticker)
    except ClientError as exc:
        report.fail(ticker, "quote", exc)
        row["last_error"] = f"quote: {exc}"
    else:
        row.update(
            price=quote.price,
            change=quote.change,
            pct_change=quote.pct_change,
            day_open=quote.day_open,
            day_high=quote.day_high,
            day_low=quote.day_low,
            prev_close=quote.prev_close,
            quote_at=quote.at,
        )
        report.quotes += 1

    stale = (
        existing is None
        or existing.profile_refreshed_at is None
        or utcnow() - _aware(existing.profile_refreshed_at) > PROFILE_MAX_AGE
    )
    if stale:
        try:
            profile = await finnhub.profile(ticker)
            # Finnhub's profile describes the *company*: for TD or SHOP that is
            # its home market (Toronto, CAD). The quote above is the US listing
            # in US dollars, so the row must say so, or a portfolio would read a
            # USD price as CAD. Keep the listing's exchange if we already have it.
            profile["currency"] = "USD"
            if existing is not None and existing.exchange:
                profile.pop("exchange", None)
            row.update(profile)
            row["profile_refreshed_at"] = utcnow()
        except ClientError as exc:
            report.fail(ticker, "profile", exc)
    # Fundamentals move daily (P/E follows price); one call each per refresh.
    try:
        row["metrics"] = await finnhub.metrics(ticker)
        row["recommendation"] = await finnhub.recommendation(ticker)
    except ClientError as exc:
        report.fail(ticker, "metrics", exc)

    await _upsert_rows(db, Security.__table__, [row], ["ticker"])
    return row["last_error"] is None


async def refresh_foreign_security(
    db: Database, yahoo: YahooChartClient, ticker: str, *, report: HubReport | None = None
) -> bool:
    """Profile and quote for a non-US listing (``VFV.TO``) from Yahoo alone.

    Finnhub's free plan refuses these symbols, so there are no fundamentals or
    analyst trends for them; the row still carries its real name, exchange and
    *currency*, which the portfolio needs to convert it correctly.
    """
    report = report or HubReport()
    row: dict[str, Any] = {"ticker": ticker, "refreshed_at": utcnow(), "last_error": None}
    try:
        snap = await yahoo.snapshot(ticker)
    except ClientError as exc:
        report.fail(ticker, "quote", exc)
        snap, row["last_error"] = None, f"quote: {exc}"
    if snap is None and row["last_error"] is None:
        row["last_error"] = "quote: no such listing on Yahoo"
    if snap:
        row.update(snap)
        row["profile_refreshed_at"] = utcnow()
    await _upsert_rows(db, Security.__table__, [row], ["ticker"])
    return row["last_error"] is None


def _aware(when: datetime) -> datetime:
    return when if when.tzinfo else when.replace(tzinfo=UTC)


# ── price history ────────────────────────────────────────────────────────────
def _range_for(last: date | None, today: date) -> str:
    """Smallest Yahoo range that covers the gap since the last stored bar."""
    if last is None:
        return "5y"
    gap = (today - last).days
    for days, label in ((25, "1mo"), (85, "3mo"), (360, "1y"), (720, "2y")):
        if gap <= days:
            return label
    return "5y"


async def refresh_prices(
    db: Database, yahoo: YahooChartClient, ticker: str, *, report: HubReport | None = None
) -> int:
    """Fetch daily bars, incrementally after the first backfill. Returns bars written."""
    report = report or HubReport()
    async with db.session() as session:
        last = await session.scalar(
            select(func.max(PriceBar.date)).where(PriceBar.ticker == ticker)
        )
    try:
        bars = await yahoo.daily_bars(ticker, range_=_range_for(last, date.today()))
    except ClientError as exc:
        report.fail(ticker, "prices", exc)
        return 0
    # Re-write the last stored day too: it may have been an intraday partial bar.
    rows = [
        {
            "ticker": ticker,
            "date": bar.date,
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "adj_close": bar.adj_close,
            "volume": bar.volume,
        }
        for bar in bars
        if last is None or bar.date >= last
    ]
    await _upsert_rows(db, PriceBar.__table__, rows, ["ticker", "date"])
    report.bars += len(rows)
    return len(rows)


# ── company news ─────────────────────────────────────────────────────────────
def normalize_news_item(item: dict[str, Any]) -> dict[str, Any] | None:
    """Map one Finnhub company-news item to a ``statuses`` row (None if unusable)."""
    headline = (item.get("headline") or "").strip()
    if not headline or not item.get("id"):
        return None
    summary = (item.get("summary") or "").strip()
    text = f"{headline}\n\n{summary}" if summary else headline
    stamp = item.get("datetime")
    return {
        "id": f"mkt:{item['id']}",
        "account_id": MARKET_ACCOUNT["id"],
        "created_at": datetime.fromtimestamp(stamp, UTC) if stamp else datetime.now(UTC),
        "url": item.get("url"),
        "uri": item.get("url"),
        "content_text": text,
        "content_hash": content_hash(content=text),
        "kind": item.get("source") or "Finnhub",
        "visibility": "public",
        "source": NEWS_SOURCE,
        "raw": item,
    }


def _related(item: dict[str, Any], queried: str, tracked: set[str]) -> set[str]:
    """The queried ticker plus any other tracked ticker the provider tagged."""
    tagged = {t.strip().upper() for t in (item.get("related") or "").split(",") if t.strip()}
    return {queried} | (tagged & tracked)


async def ingest_company_news(
    db: Database,
    finnhub: FinnhubClient,
    tickers: Iterable[str],
    *,
    days: int = 7,
    report: HubReport | None = None,
) -> int:
    """Archive recent company news for each ticker. Idempotent. Returns items written."""
    report = report or HubReport()
    tracked = set(tickers)
    end = date.today()
    start = end - timedelta(days=days)
    seen_titles: set[str] = set()
    written = 0

    async with db.session() as session, session.begin():
        await AccountRepository(session, db.dialect).upsert(dict(MARKET_ACCOUNT))

    for ticker in sorted(tracked):
        try:
            items = await finnhub.company_news(ticker, start, end)
        except ClientError as exc:
            report.fail(ticker, "news", exc)
            continue
        items.sort(key=lambda i: i.get("datetime") or 0, reverse=True)
        for item in items[:NEWS_PER_TICKER]:
            row = normalize_news_item(item)
            if row is None:
                continue
            # The same wire story is often syndicated under several ids.
            title_key = row["content_text"].split("\n", 1)[0].lower()
            if title_key in seen_titles:
                continue
            seen_titles.add(title_key)
            async with db.session() as session, session.begin():
                await StatusRepository(session, db.dialect).upsert(row)
                mentions = StockMentionRepository(session, db.dialect)
                for symbol in _related(item, ticker, tracked):
                    await mentions.upsert(
                        {"status_id": row["id"], "ticker": symbol, "alias": NEWS_ALIAS}
                    )
            written += 1
    report.news += written
    return written


async def refresh_all(
    db: Database,
    finnhub: FinnhubClient,
    yahoo: YahooChartClient,
    *,
    tickers: list[str] | None = None,
    news_days: int = 7,
    prices: bool = True,
    news: bool = True,
) -> HubReport:
    """The scheduled job: quotes, fundamentals, prices and news for tracked tickers."""
    report = HubReport()
    symbols = tickers if tickers is not None else await tracked_tickers(db)
    report.tickers = len(symbols)
    for ticker in symbols:
        if is_foreign(ticker):
            await refresh_foreign_security(db, yahoo, ticker, report=report)
        else:
            await refresh_security(db, finnhub, ticker, report=report)
        if prices:
            await refresh_prices(db, yahoo, ticker, report=report)
    us = [t for t in symbols if not is_foreign(t)]  # Finnhub news is US-only on free
    if news and us:
        await ingest_company_news(db, finnhub, us, days=news_days, report=report)
    return report
