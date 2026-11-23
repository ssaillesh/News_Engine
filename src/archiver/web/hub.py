"""Investment hub API: securities, prices, ticker news, watchlist, holdings, portfolio.

Mounted under ``/api/hub`` by :func:`archiver.web.app.create_app`. Reads serve
stored data, so pages never wait on a provider; ``?refresh=true`` on a ticker
fetches live first when a Finnhub key is configured.

Whenever ``HUB_WRITE_TOKEN`` is set, the ``X-Hub-Token`` header is required on
writes (watchlist, holdings) and on reads that expose positions (holdings,
portfolio, shares held), so a public deployment can be neither edited nor
read for its portfolio by anyone who finds the URL. Without the token those
reads degrade (no totals, no held tickers) rather than fail, except the
holdings and portfolio endpoints themselves, which return 401.
"""

from __future__ import annotations

import hmac
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Float, cast, func, select
from sqlalchemy.orm import selectinload

from archiver.clients.exceptions import ClientError
from archiver.clients.market import FinnhubClient, YahooChartClient
from archiver.config.settings import get_settings
from archiver.hub.portfolio import Lot, summarize
from archiver.hub.service import normalize_ticker, refresh_prices, refresh_security
from archiver.storage.db import Database
from archiver.storage.models import (
    Holding,
    PriceBar,
    Security,
    Status,
    StatusImpact,
    StatusSentiment,
    StockMention,
    WatchlistItem,
)

RANGES = {"1m": 31, "3m": 92, "6m": 183, "ytd": None, "1y": 366, "5y": 1830, "max": None}


# ── request bodies ───────────────────────────────────────────────────────────
class _TickerBody(BaseModel):
    ticker: str

    @field_validator("ticker")
    @classmethod
    def _ticker(cls, value: str) -> str:
        return normalize_ticker(value)


class WatchIn(_TickerBody):
    note: str | None = Field(None, max_length=2000)


class HoldingIn(_TickerBody):
    shares: float = Field(gt=0)
    avg_cost: float = Field(ge=0)
    opened_at: date | None = None
    note: str | None = Field(None, max_length=2000)


class HoldingPatch(BaseModel):
    shares: float | None = Field(None, gt=0)
    avg_cost: float | None = Field(None, ge=0)
    opened_at: date | None = None
    note: str | None = Field(None, max_length=2000)


# ── serializers ──────────────────────────────────────────────────────────────
def security_dict(sec: Security | None, ticker: str) -> dict[str, Any]:
    if sec is None:
        return {"ticker": ticker, "tracked_data": False}
    return {
        "ticker": sec.ticker,
        "tracked_data": True,
        "name": sec.name,
        "exchange": sec.exchange,
        "currency": sec.currency,
        "country": sec.country,
        "industry": sec.industry,
        "logo_url": sec.logo_url,
        "web_url": sec.web_url,
        "ipo_date": sec.ipo_date,
        "market_cap": sec.market_cap,
        "quote": {
            "price": sec.price,
            "change": sec.change,
            "pct_change": sec.pct_change,
            "open": sec.day_open,
            "high": sec.day_high,
            "low": sec.day_low,
            "prev_close": sec.prev_close,
            "at": sec.quote_at.isoformat() if sec.quote_at else None,
        },
        "metrics": sec.metrics or {},
        "recommendation": sec.recommendation,
        "last_error": sec.last_error,
        "refreshed_at": sec.refreshed_at.isoformat() if sec.refreshed_at else None,
    }


def _holding_dict(h: Holding) -> dict[str, Any]:
    return {
        "id": h.id,
        "ticker": h.ticker,
        "shares": h.shares,
        "avg_cost": h.avg_cost,
        "opened_at": h.opened_at.isoformat() if h.opened_at else None,
        "note": h.note,
    }


def build_hub_router(db: Database, to_item: Callable[[Status], dict[str, Any]]) -> APIRouter:
    """``to_item`` is the feed's card serializer, passed in to avoid a circular import."""
    router = APIRouter(prefix="/api/hub", tags=["hub"])
    settings = get_settings()

    def authorized(x_hub_token: str | None = Header(None)) -> bool:
        expected = get_settings().hub_write_token
        return not expected or hmac.compare_digest(x_hub_token or "", expected)

    def require_token(ok: bool = Depends(authorized)) -> None:
        if not ok:
            raise HTTPException(401, "missing or invalid X-Hub-Token")

    def _ticker(raw: str) -> str:
        try:
            return normalize_ticker(raw)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    async def _live_refresh(ticker: str, *, prices: bool = False) -> None:
        """Best effort: a provider outage must not turn a read into an error."""
        if not settings.finnhub_api_key:
            return
        try:
            async with FinnhubClient.from_settings(settings) as finnhub:
                await refresh_security(db, finnhub, ticker)
            if prices:
                async with YahooChartClient.from_settings(settings) as yahoo:
                    await refresh_prices(db, yahoo, ticker)
        except ClientError:
            pass

    async def _securities(tickers: list[str]) -> dict[str, Security]:
        if not tickers:
            return {}
        async with db.session() as session:
            rows = await session.scalars(select(Security).where(Security.ticker.in_(tickers)))
            return {s.ticker: s for s in rows.all()}

    def _news_query(tickers: list[str], since: datetime | None) -> Any:
        stmt = (
            select(Status)
            # IN-subquery rather than a join: no duplicate rows and no DISTINCT,
            # which Postgres would reject alongside ORDER BY impact_score.
            .where(
                Status.id.in_(
                    select(StockMention.status_id).where(StockMention.ticker.in_(tickers))
                ),
                Status.is_deleted.is_(False),
            )
            .options(
                selectinload(Status.sentiment),
                selectinload(Status.summary),
                selectinload(Status.impact),
                selectinload(Status.topics),
                selectinload(Status.entities),
                selectinload(Status.stock_mentions),
                selectinload(Status.sectors),
            )
        )
        if since is not None:
            stmt = stmt.where(Status.created_at >= since)
        return stmt

    # ── search & securities ──────────────────────────────────────────────────
    @router.get("/search")
    async def search(q: str = Query(..., min_length=1, max_length=40)) -> dict[str, Any]:
        """Ticker lookup: stored securities first, then Finnhub when configured."""
        needle = q.strip().upper()
        async with db.session() as session:
            local = (
                await session.scalars(
                    select(Security)
                    .where(
                        (Security.ticker.like(f"{needle}%"))
                        | (func.upper(Security.name).like(f"%{needle}%"))
                    )
                    # Exact ticker first, then core names, then shortest tickers.
                    .order_by(
                        (Security.ticker == needle).desc(),
                        Security.is_core.desc(),
                        func.length(Security.ticker),
                        Security.ticker,
                    )
                    .limit(10)
                )
            ).all()
        results = [{"ticker": s.ticker, "name": s.name or ""} for s in local]
        if settings.finnhub_api_key and len(results) < 10:
            try:
                async with FinnhubClient.from_settings(settings) as finnhub:
                    remote = await finnhub.search(q)
            except ClientError:
                remote = []
            have = {r["ticker"] for r in results}
            results += [r for r in remote if r["ticker"] not in have][: 10 - len(results)]
        return {"results": results}

    @router.get("/securities")
    async def list_securities(
        scope: str = Query("core", pattern="^(core|all)$"),
        q: str | None = Query(None, max_length=40),
        sector: str | None = Query(None, max_length=64),
        sort: str = Query("market_cap", pattern="^(ticker|name|price|pct_change|market_cap)$"),
        order: str = Query("desc", pattern="^(asc|desc)$"),
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        """Browse the universe: core symbols by default, every listed one with scope=all."""
        stmt = select(Security)
        if scope == "core":
            stmt = stmt.where(Security.is_core.is_(True))
        if q:
            needle = q.strip().upper()
            stmt = stmt.where(
                Security.ticker.like(f"{needle}%") | func.upper(Security.name).like(f"%{needle}%")
            )
        if sector:
            stmt = stmt.where(Security.sector == sector)
        column = getattr(Security, sort)
        ordered = column.desc() if order == "desc" else column.asc()
        async with db.session() as session:
            total = await session.scalar(select(func.count()).select_from(stmt.subquery()))
            rows = (
                await session.scalars(
                    stmt.order_by(ordered.nulls_last(), Security.ticker).limit(limit).offset(offset)
                )
            ).all()
        return {
            "total": total or 0,
            "items": [
                {
                    "ticker": s.ticker,
                    "name": s.name,
                    "sector": s.sector,
                    "type": s.security_type,
                    "tags": s.tags or [],
                    "price": s.price,
                    "change": s.change,
                    "pct_change": s.pct_change,
                    "market_cap": s.market_cap,
                    "quote_at": s.quote_at.isoformat() if s.quote_at else None,
                }
                for s in rows
            ],
        }

    @router.get("/sectors")
    async def sectors() -> dict[str, Any]:
        """Core symbols per sector, for the browse page's filter."""
        async with db.session() as session:
            rows = (
                await session.execute(
                    select(Security.sector, func.count())
                    .where(Security.is_core.is_(True), Security.sector.is_not(None))
                    .group_by(Security.sector)
                    .order_by(func.count().desc())
                )
            ).all()
        return {"sectors": [{"sector": s, "count": n} for s, n in rows]}

    @router.get("/securities/{ticker}")
    async def security(
        ticker: str, refresh: bool = False, ok: bool = Depends(authorized)
    ) -> dict[str, Any]:
        symbol = _ticker(ticker)
        if refresh:
            await _live_refresh(symbol)
        async with db.session() as session:
            sec = await session.get(Security, symbol)
            watched = await session.get(WatchlistItem, symbol) is not None
            held = await session.scalar(
                select(func.coalesce(func.sum(Holding.shares), 0)).where(Holding.ticker == symbol)
            )
        if sec is None and not refresh and settings.finnhub_api_key:
            await _live_refresh(symbol, prices=True)  # first visit: fill it in
            async with db.session() as session:
                sec = await session.get(Security, symbol)
        return {
            **security_dict(sec, symbol),
            "watched": watched,
            "shares_held": (held or 0) if ok else None,
        }

    @router.get("/securities/{ticker}/prices")
    async def prices(
        ticker: str, range: str = Query("1y", pattern="^(1m|3m|6m|ytd|1y|5y|max)$")
    ) -> dict[str, Any]:
        """Daily bars, period stats, and per-day news markers for the chart."""
        symbol = _ticker(ticker)
        today = date.today()
        days = RANGES[range]
        start = (
            date(today.year, 1, 1)
            if range == "ytd"
            else (today - timedelta(days=days) if days else None)
        )
        async with db.session() as session:
            stmt = select(PriceBar).where(PriceBar.ticker == symbol).order_by(PriceBar.date)
            if start:
                stmt = stmt.where(PriceBar.date >= start)
            bars = (await session.scalars(stmt)).all()

            # One marker per day with news: count, mean sentiment, peak impact.
            day = func.date(Status.created_at)
            marker_stmt = (
                select(
                    day.label("day"),
                    func.count(func.distinct(Status.id)),
                    func.avg(cast(StatusSentiment.compound, Float)),
                    func.max(StatusImpact.impact_score),
                )
                .join(StockMention, StockMention.status_id == Status.id)
                .outerjoin(StatusSentiment, StatusSentiment.status_id == Status.id)
                .outerjoin(StatusImpact, StatusImpact.status_id == Status.id)
                .where(StockMention.ticker == symbol)
                .group_by(day)
                .order_by(day)
            )
            if start:
                marker_stmt = marker_stmt.where(
                    Status.created_at >= datetime.combine(start, datetime.min.time(), UTC)
                )
            markers = (await session.execute(marker_stmt)).all()

        closes = [b.close for b in bars if b.close is not None]
        stats = None
        if closes:
            stats = {
                "start": closes[0],
                "end": closes[-1],
                "return_pct": round((closes[-1] / closes[0] - 1) * 100, 2) if closes[0] else None,
                "high": max(b.high or b.close for b in bars if b.close is not None),
                "low": min(b.low or b.close for b in bars if b.close is not None),
            }
        return {
            "ticker": symbol,
            "range": range,
            "bars": [
                {
                    "date": b.date.isoformat(),
                    "open": b.open,
                    "high": b.high,
                    "low": b.low,
                    "close": b.close,
                    "adj_close": b.adj_close,
                    "volume": b.volume,
                }
                for b in bars
            ],
            "stats": stats,
            "news_markers": [
                {
                    "date": str(m[0]),
                    "count": m[1],
                    "avg_sentiment": round(m[2], 3) if m[2] is not None else None,
                    "max_impact": round(m[3], 3) if m[3] is not None else None,
                }
                for m in markers
            ],
        }

    @router.get("/securities/{ticker}/news")
    async def ticker_news(
        ticker: str,
        sort: str = Query("recent", pattern="^(recent|impact)$"),
        limit: int = Query(25, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        symbol = _ticker(ticker)
        stmt = _news_query([symbol], None)
        if sort == "impact":
            stmt = stmt.outerjoin(StatusImpact, StatusImpact.status_id == Status.id).order_by(
                StatusImpact.impact_score.desc().nulls_last(), Status.created_at.desc()
            )
        else:
            stmt = stmt.order_by(Status.created_at.desc())
        async with db.session() as session:
            rows = (await session.scalars(stmt.limit(limit).offset(offset))).unique().all()
        return {"ticker": symbol, "items": [to_item(s) for s in rows]}

    # ── watchlist ────────────────────────────────────────────────────────────
    @router.get("/watchlist")
    async def watchlist() -> dict[str, Any]:
        async with db.session() as session:
            result = await session.scalars(select(WatchlistItem).order_by(WatchlistItem.ticker))
            items = result.all()
        secs = await _securities([i.ticker for i in items])
        return {
            "items": [
                {
                    **security_dict(secs.get(i.ticker), i.ticker),
                    "note": i.note,
                    "added_at": i.added_at.isoformat(),
                }
                for i in items
            ]
        }

    @router.post("/watchlist", status_code=201, dependencies=[Depends(require_token)])
    async def watch(body: WatchIn) -> dict[str, Any]:
        async with db.session() as session, session.begin():
            item = await session.get(WatchlistItem, body.ticker)
            if item is None:
                session.add(WatchlistItem(ticker=body.ticker, note=body.note))
            elif body.note is not None:
                item.note = body.note
        await _live_refresh(body.ticker, prices=True)
        return {"ticker": body.ticker, "watched": True}

    @router.delete("/watchlist/{ticker}", dependencies=[Depends(require_token)])
    async def unwatch(ticker: str) -> dict[str, Any]:
        symbol = _ticker(ticker)
        async with db.session() as session, session.begin():
            item = await session.get(WatchlistItem, symbol)
            if item is None:
                raise HTTPException(404, f"{symbol} is not on the watchlist")
            await session.delete(item)
        return {"ticker": symbol, "watched": False}

    # ── holdings & portfolio ─────────────────────────────────────────────────
    @router.get("/holdings", dependencies=[Depends(require_token)])
    async def holdings() -> dict[str, Any]:
        async with db.session() as session:
            rows = await session.scalars(select(Holding).order_by(Holding.ticker, Holding.id))
            return {"items": [_holding_dict(h) for h in rows.all()]}

    @router.post("/holdings", status_code=201, dependencies=[Depends(require_token)])
    async def add_holding(body: HoldingIn) -> dict[str, Any]:
        async with db.session() as session, session.begin():
            row = Holding(**body.model_dump())
            session.add(row)
            await session.flush()
            out = _holding_dict(row)
        await _live_refresh(body.ticker, prices=True)
        return out

    @router.patch("/holdings/{holding_id}", dependencies=[Depends(require_token)])
    async def edit_holding(holding_id: int, body: HoldingPatch) -> dict[str, Any]:
        async with db.session() as session, session.begin():
            row = await session.get(Holding, holding_id)
            if row is None:
                raise HTTPException(404, "holding not found")
            for key, value in body.model_dump(exclude_unset=True).items():
                setattr(row, key, value)
            return _holding_dict(row)

    @router.delete("/holdings/{holding_id}", dependencies=[Depends(require_token)])
    async def delete_holding(holding_id: int) -> dict[str, Any]:
        async with db.session() as session, session.begin():
            row = await session.get(Holding, holding_id)
            if row is None:
                raise HTTPException(404, "holding not found")
            await session.delete(row)
        return {"deleted": holding_id}

    async def _portfolio() -> dict[str, Any]:
        async with db.session() as session:
            lots = (await session.scalars(select(Holding))).all()
        secs = await _securities(sorted({h.ticker for h in lots}))
        quotes = {
            t: {"price": s.price, "change": s.change, "pct_change": s.pct_change, "name": s.name}
            for t, s in secs.items()
        }
        return summarize([Lot(h.ticker, h.shares, h.avg_cost) for h in lots], quotes)

    @router.get("/portfolio", dependencies=[Depends(require_token)])
    async def portfolio() -> dict[str, Any]:
        return await _portfolio()

    # ── dashboard ────────────────────────────────────────────────────────────
    @router.get("/dashboard")
    async def dashboard(
        days: int = Query(7, ge=1, le=90), ok: bool = Depends(authorized)
    ) -> dict[str, Any]:
        """Home page in one call: watchlist movers, portfolio totals, top news."""
        async with db.session() as session:
            watched = (await session.scalars(select(WatchlistItem.ticker))).all()
            held = (await session.scalars(select(Holding.ticker).distinct())).all() if ok else []
        tickers = sorted({*watched, *held})
        secs = await _securities(tickers)
        movers = sorted(
            (security_dict(s, t) for t, s in secs.items() if s.pct_change is not None),
            key=lambda d: abs(d["quote"]["pct_change"]),
            reverse=True,
        )
        top_news: list[dict[str, Any]] = []
        if tickers:
            since = datetime.now(UTC) - timedelta(days=days)
            stmt = (
                _news_query(tickers, since)
                .outerjoin(StatusImpact, StatusImpact.status_id == Status.id)
                .order_by(StatusImpact.impact_score.desc().nulls_last(), Status.created_at.desc())
                .limit(15)
            )
            async with db.session() as session:
                top_news = [to_item(s) for s in (await session.scalars(stmt)).unique().all()]
        return {
            "tickers": tickers,
            "movers": movers[:10],
            "portfolio": (await _portfolio())["totals"] if held else None,
            "top_news": top_news,
        }

    # Kept for the frontend's sake: "is this ticker tracked at all?"
    @router.get("/tracked")
    async def tracked(ok: bool = Depends(authorized)) -> dict[str, Any]:
        async with db.session() as session:
            watched = set((await session.scalars(select(WatchlistItem.ticker))).all())
            held = set(
                (
                    await session.scalars(
                        select(Holding.ticker).where(Holding.shares > 0).distinct()
                    )
                ).all()
            )
        return {"watchlist": sorted(watched), "holdings": sorted(held) if ok else []}

    return router
