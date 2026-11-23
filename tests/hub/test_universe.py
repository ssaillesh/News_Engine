"""Universe: symbol load, core marking, EOD price sync, browse API. No network."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime

import httpx
import pytest
from httpx import ASGITransport

from archiver.clients.market import FinnhubClient, PolygonClient, parse_grouped
from archiver.clients.rate_limit import NullRateLimiter
from archiver.hub.universe import _trading_days, sync_core_eod, sync_universe
from archiver.storage.db import Database
from archiver.storage.models import PriceBar, Security
from archiver.web import create_app

SP500 = {
    "AAPL": {"name": "Apple Inc.", "sector": "Information Technology"},
    "XOM": {"name": "ExxonMobil", "sector": "Energy"},
}
SYMBOLS = [
    {"symbol": "AAPL", "description": "APPLE INC", "type": "Common Stock", "mic": "XNAS"},
    {"symbol": "XOM", "description": "EXXON MOBIL CORP", "type": "Common Stock", "mic": "XNYS"},
    {"symbol": "ZZZQ", "description": "SMALL CO", "type": "Common Stock", "mic": "XNAS"},
    {"symbol": "SPY", "description": "SPDR S&P 500", "type": "ETP", "mic": "ARCX"},
    {"symbol": "OTCX", "description": "OTC THING", "type": "Common Stock", "mic": "OOTC"},
    {"symbol": "WARR", "description": "A WARRANT", "type": "Warrant", "mic": "XNAS"},
]


def _finnhub() -> FinnhubClient:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/stock/symbol")
        return httpx.Response(200, json=SYMBOLS)

    return FinnhubClient(
        "k",
        transport=httpx.MockTransport(handler),
        user_agent="t",
        max_retries=0,
        rate_limiter=NullRateLimiter(),
    )


def _grouped(day: str) -> dict:
    closes = {"2026-11-19": (100.0, 50.0), "2026-11-20": (110.0, 49.0)}.get(day)
    if closes is None:
        return {"resultsCount": 0, "results": []}
    aapl, xom = closes
    return {
        "results": [
            {"T": "AAPL", "o": aapl, "h": aapl, "l": aapl, "c": aapl, "v": 1e6},
            {"T": "XOM", "o": xom, "h": xom, "l": xom, "c": xom, "v": 2e6},
            {"T": "ZZZQ", "o": 1, "h": 1, "l": 1, "c": 1, "v": 10},  # not core: ignored
        ]
    }


def _polygon() -> PolygonClient:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer pk"
        return httpx.Response(200, json=_grouped(request.url.path.rsplit("/", 1)[1]))

    return PolygonClient(
        "pk",
        transport=httpx.MockTransport(handler),
        user_agent="t",
        max_retries=0,
        rate_limiter=NullRateLimiter(),
    )


def test_parse_grouped_and_trading_days():
    bars = parse_grouped(_grouped("2026-11-19"), date(2026, 11, 19))
    assert bars["AAPL"].close == 100.0 and bars["AAPL"].volume == 1_000_000
    assert parse_grouped({"resultsCount": 0}, date(2026, 11, 22)) == {}
    # Fri 20th .. Mon 23rd skips the weekend.
    assert _trading_days(date(2026, 11, 20), date(2026, 11, 23)) == [
        date(2026, 11, 20),
        date(2026, 11, 23),
    ]


async def test_sync_universe_marks_core(db: Database):
    async with _finnhub() as finnhub:
        report = await sync_universe(db, finnhub, sp500=SP500)
    async with db.session() as session:
        aapl = await session.get(Security, "AAPL")
        small = await session.get(Security, "ZZZQ")
        spy = await session.get(Security, "SPY")
        assert await session.get(Security, "OTCX") is None  # OTC excluded
        assert await session.get(Security, "WARR") is None  # warrants excluded
    assert aapl.is_core and aapl.tags == ["SP500"] and aapl.sector == "Information Technology"
    assert aapl.name == "Apple Inc."
    assert not small.is_core and small.name == "Small Co"
    assert spy.is_core and "ETF" in spy.tags and spy.sector == "ETF"
    assert report.sp500 == 2 and report.core > 2

    # A stock leaving the S&P 500 loses its core flag on the next sync.
    async with _finnhub() as finnhub:
        await sync_universe(db, finnhub, sp500={"AAPL": SP500["AAPL"]})
    async with db.session() as session:
        assert not (await session.get(Security, "XOM")).is_core


async def test_eod_sync_writes_core_bars_and_quotes(db: Database):
    async with _finnhub() as finnhub:
        await sync_universe(db, finnhub, sp500=SP500)
    # A newer live quote must survive the end-of-day update.
    async with db.session() as session, session.begin():
        xom = await session.get(Security, "XOM")
        xom.price, xom.quote_at = 51.5, datetime(2026, 11, 21, 15, tzinfo=UTC)

    async with _polygon() as polygon:
        report = await sync_core_eod(db, polygon, today=date(2026, 11, 23))
    assert report.days == ["2026-11-19", "2026-11-20"]
    async with db.session() as session:
        bars = (
            await session.scalars(PriceBar.__table__.select().where(PriceBar.ticker == "ZZZQ"))
        ).all()
        assert bars == []
        aapl = await session.get(Security, "AAPL")
        xom = await session.get(Security, "XOM")
    assert aapl.price == 110.0 and aapl.prev_close == 100.0 and aapl.pct_change == 10.0
    assert xom.price == 51.5  # live quote kept

    # Nothing new on a re-run the same day.
    async with _polygon() as polygon:
        again = await sync_core_eod(db, polygon, today=date(2026, 11, 23))
    assert again.days == []


@pytest.fixture
async def client(db: Database, monkeypatch) -> AsyncIterator[httpx.AsyncClient]:
    monkeypatch.setenv("FINNHUB_API_KEY", "")
    monkeypatch.setenv("HUB_WRITE_TOKEN", "")
    from archiver.config import settings as settings_mod

    settings_mod.get_settings.cache_clear()
    async with httpx.AsyncClient(
        transport=ASGITransport(app=create_app(db)), base_url="http://test"
    ) as c:
        yield c


async def test_browse_api(client: httpx.AsyncClient, db: Database):
    async with _finnhub() as finnhub:
        await sync_universe(db, finnhub, sp500=SP500)
    async with _polygon() as polygon:
        await sync_core_eod(db, polygon, today=date(2026, 11, 23))

    core = (await client.get("/api/hub/securities?sort=pct_change")).json()
    assert core["items"][0]["ticker"] == "AAPL"  # +10% leads
    assert "ZZZQ" not in {i["ticker"] for i in core["items"]}
    every = (await client.get("/api/hub/securities?scope=all&limit=200")).json()
    assert every["total"] > core["total"]
    energy = (await client.get("/api/hub/securities?sector=Energy")).json()
    assert [i["ticker"] for i in energy["items"]] == ["XOM"]
    sectors = (await client.get("/api/hub/sectors")).json()["sectors"]
    assert {"sector": "Energy", "count": 1} in sectors
    found = (await client.get("/api/hub/search?q=aapl")).json()["results"]
    assert found[0]["ticker"] == "AAPL"
