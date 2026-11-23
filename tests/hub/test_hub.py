"""Investment hub: provider parsing, portfolio math, refresh service and API.

No network: providers are faked with httpx.MockTransport.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from httpx import ASGITransport

from archiver.clients.market import FinnhubClient, YahooChartClient, parse_chart
from archiver.clients.rate_limit import NullRateLimiter
from archiver.hub.portfolio import Lot, summarize
from archiver.hub.service import (
    _range_for,
    ingest_company_news,
    normalize_ticker,
    refresh_all,
)
from archiver.storage.db import Database
from archiver.storage.models import PriceBar, Security, StockMention, WatchlistItem
from archiver.web import create_app

NOW = int(datetime(2026, 11, 19, 15, tzinfo=UTC).timestamp())


def _finnhub_handler(request: httpx.Request) -> httpx.Response:
    assert request.headers["X-Finnhub-Token"] == "test-key"
    assert "token" not in request.url.params  # key never in the URL
    symbol = request.url.params.get("symbol", "")
    path = request.url.path.removeprefix("/api/v1")
    if path == "/quote":
        if symbol == "NOPE":
            body = {"c": 0, "d": None, "dp": None, "h": 0, "l": 0, "o": 0, "pc": 0, "t": 0}
        else:
            body = {
                "c": 110.0,
                "d": 2.0,
                "dp": 1.85,
                "h": 111,
                "l": 107,
                "o": 108,
                "pc": 108.0,
                "t": NOW,
            }
    elif path == "/stock/profile2":
        body = {
            "name": f"{symbol} Inc",
            "exchange": "NASDAQ",
            "currency": "USD",
            "country": "US",
            "finnhubIndustry": "Technology",
            "marketCapitalization": 2500.5,
            "shareOutstanding": 20.0,
        }
    elif path == "/stock/metric":
        body = {"metric": {"peTTM": 28.4, "52WeekHigh": 120, "junk": "x", "beta": None}}
    elif path == "/stock/recommendation":
        body = [
            {
                "period": "2026-10-01",
                "buy": 10,
                "hold": 5,
                "sell": 1,
                "strongBuy": 3,
                "strongSell": 0,
            },
            {
                "period": "2026-11-01",
                "buy": 12,
                "hold": 4,
                "sell": 1,
                "strongBuy": 4,
                "strongSell": 0,
            },
        ]
    elif path == "/company-news":
        base = sum(map(ord, symbol)) * 10  # Finnhub ids are unique per article
        body = [
            {
                "id": base + 1,
                "datetime": NOW,
                "headline": f"{symbol} beats estimates",
                "summary": "Revenue up.",
                "source": "Reuters",
                "url": "https://x/1",
                "related": f"{symbol},MSFT",
            },
            {
                "id": base + 2,
                "datetime": NOW - 60,
                "headline": f"{symbol} beats estimates",
                "summary": "Same story, syndicated.",
                "source": "Yahoo",
                "url": "https://x/2",
                "related": symbol,
            },
            {"id": base + 3, "datetime": NOW - 120, "headline": "", "summary": "no headline"},
        ]
    elif path == "/search":
        body = {
            "result": [
                {"symbol": "AAPL", "description": "APPLE INC", "type": "Common Stock"},
                {"symbol": "AAPL.MX", "description": "APPLE INC", "type": "Common Stock"},
                {"symbol": "BRK.B", "description": "BERKSHIRE", "type": "Common Stock"},
            ]
        }
    else:
        return httpx.Response(404, json={"error": "unknown"})
    return httpx.Response(200, json=body)


def _chart(days: int = 3) -> dict:
    start = int(datetime(2026, 11, 16, 14, 30, tzinfo=UTC).timestamp())
    stamps = [start + i * 86400 for i in range(days)]
    closes = [100.0 + i for i in range(days)]
    closes[1] = None  # a partial row must be dropped
    return {
        "chart": {
            "error": None,
            "result": [
                {
                    "timestamp": stamps,
                    "indicators": {
                        "quote": [
                            {
                                "open": closes,
                                "high": closes,
                                "low": closes,
                                "close": closes,
                                "volume": [1000] * days,
                            }
                        ],
                        "adjclose": [{"adjclose": closes}],
                    },
                }
            ],
        }
    }


def _yahoo_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=_chart())


def _clients() -> tuple[FinnhubClient, YahooChartClient]:
    finnhub = FinnhubClient(
        "test-key",
        transport=httpx.MockTransport(_finnhub_handler),
        user_agent="t",
        max_retries=0,
        rate_limiter=NullRateLimiter(),
    )
    yahoo = YahooChartClient(transport=httpx.MockTransport(_yahoo_handler), max_retries=0)
    return finnhub, yahoo


# ── pure helpers ─────────────────────────────────────────────────────────────
def test_normalize_ticker():
    assert normalize_ticker(" aapl ") == "AAPL"
    assert normalize_ticker("brk.b") == "BRK.B"
    with pytest.raises(ValueError):
        normalize_ticker("DROP TABLE")


def test_range_for_is_incremental():
    today = date(2026, 11, 20)
    assert _range_for(None, today) == "5y"
    assert _range_for(today - timedelta(days=3), today) == "1mo"
    assert _range_for(today - timedelta(days=200), today) == "1y"


def test_parse_chart_drops_partial_rows():
    bars = parse_chart(_chart(), "AAPL")
    assert [b.close for b in bars] == [100.0, 102.0]
    assert bars[0].date == date(2026, 11, 16)


def test_parse_chart_error():
    from archiver.clients.exceptions import NotFoundError

    with pytest.raises(NotFoundError):
        parse_chart({"chart": {"error": {"code": "Not Found"}, "result": None}}, "ZZZZ")


def test_portfolio_summary():
    out = summarize(
        [Lot("AAPL", 10, 100.0), Lot("aapl", 10, 120.0), Lot("XYZ", 5, 10.0)],
        {"AAPL": {"price": 130.0, "change": 2.0, "pct_change": 1.56, "name": "Apple"}},
    )
    aapl = out["positions"][0]
    assert aapl["ticker"] == "AAPL" and aapl["shares"] == 20 and aapl["lots"] == 2
    assert aapl["avg_cost"] == 110.0
    assert aapl["market_value"] == 2600.0 and aapl["unrealized_pnl"] == 400.0
    assert aapl["weight_pct"] == 100.0 and aapl["day_change"] == 40.0
    assert out["unpriced"] == ["XYZ"]
    # Unpriced positions stay out of P&L, but their cost is still reported.
    assert out["totals"]["unrealized_pnl"] == 400.0
    assert out["totals"]["cost_basis"] == 2250.0


# ── clients ──────────────────────────────────────────────────────────────────
async def test_finnhub_parsing():
    finnhub, _ = _clients()
    async with finnhub:
        quote = await finnhub.quote("AAPL")
        assert quote.price == 110.0 and quote.at is not None
        profile = await finnhub.profile("AAPL")
        assert profile["market_cap"] == pytest.approx(2.5005e9)
        assert await finnhub.metrics("AAPL") == {"peTTM": 28.4, "52WeekHigh": 120.0}
        assert (await finnhub.recommendation("AAPL"))["period"] == "2026-11-01"
        assert [r["ticker"] for r in await finnhub.search("apple")] == ["AAPL", "BRK.B"]


def test_finnhub_requires_key():
    from archiver.clients.exceptions import ClientError

    with pytest.raises(ClientError):
        FinnhubClient("", user_agent="t")


# ── service ──────────────────────────────────────────────────────────────────
async def test_refresh_all_and_news_dedup(db: Database):
    async with db.session() as session, session.begin():
        session.add_all(
            [
                WatchlistItem(ticker="AAPL"),
                WatchlistItem(ticker="MSFT"),
                WatchlistItem(ticker="NOPE"),
            ]
        )
    finnhub, yahoo = _clients()
    async with finnhub, yahoo:
        report = await refresh_all(db, finnhub, yahoo)

    assert report.tickers == 3 and report.quotes == 2
    assert "NOPE:quote" in report.errors
    async with db.session() as session:
        aapl = await session.get(Security, "AAPL")
        assert aapl.name == "AAPL Inc" and aapl.price == 110.0
        assert aapl.metrics["peTTM"] == 28.4 and aapl.profile_refreshed_at is not None
        nope = await session.get(Security, "NOPE")
        assert nope.last_error and nope.price is None
        bars = (
            await session.scalars(PriceBar.__table__.select().where(PriceBar.ticker == "AAPL"))
        ).all()
        assert len(bars) == 2
        links = (await session.execute(StockMention.__table__.select())).all()
    # Item 1 (tagged AAPL+MSFT) and its syndicated duplicate collapse into one story
    # per headline; each ticker's own headline is distinct, so AAPL/MSFT/NOPE each
    # contribute one story, and AAPL's story is also linked to MSFT.
    by_status: dict[str, set[str]] = {}
    for row in links:
        by_status.setdefault(row.status_id, set()).add(row.ticker)
    assert len(by_status) == 3
    assert {"AAPL", "MSFT"} in by_status.values()


async def test_news_ingest_is_idempotent(db: Database):
    finnhub, _ = _clients()
    async with finnhub:
        first = await ingest_company_news(db, finnhub, ["AAPL"])
        second = await ingest_company_news(db, finnhub, ["AAPL"])
    assert first == second == 1


# ── API ──────────────────────────────────────────────────────────────────────
@pytest.fixture
async def client(db: Database, monkeypatch) -> AsyncIterator[httpx.AsyncClient]:
    monkeypatch.setenv("FINNHUB_API_KEY", "")  # reads never hit a provider in tests
    monkeypatch.setenv("HUB_WRITE_TOKEN", "secret")
    monkeypatch.setenv("PORTFOLIO_CURRENCY", "USD")  # these fixtures are all USD
    from archiver.config import settings as settings_mod

    settings_mod.get_settings.cache_clear()
    transport = ASGITransport(app=create_app(db))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


AUTH = {"X-Hub-Token": "secret"}


async def test_writes_require_token(client: httpx.AsyncClient):
    resp = await client.post("/api/hub/watchlist", json={"ticker": "AAPL"})
    assert resp.status_code == 401
    resp = await client.post(
        "/api/hub/watchlist", json={"ticker": "AAPL"}, headers={"X-Hub-Token": "wrong"}
    )
    assert resp.status_code == 401


async def test_watchlist_holdings_portfolio_flow(client: httpx.AsyncClient, db: Database):
    assert (
        await client.post("/api/hub/watchlist", json={"ticker": "aapl"}, headers=AUTH)
    ).status_code == 201
    bad = await client.post("/api/hub/watchlist", json={"ticker": "not a ticker"}, headers=AUTH)
    assert bad.status_code == 422

    lot = (
        await client.post(
            "/api/hub/holdings",
            headers=AUTH,
            json={"ticker": "AAPL", "shares": 10, "avg_cost": 100},
        )
    ).json()
    patched = await client.patch(
        f"/api/hub/holdings/{lot['id']}", headers=AUTH, json={"shares": 20}
    )
    assert patched.json()["shares"] == 20

    finnhub, yahoo = _clients()
    async with finnhub, yahoo:
        await refresh_all(db, finnhub, yahoo)

    portfolio = (await client.get("/api/hub/portfolio", headers=AUTH)).json()
    assert portfolio["totals"]["market_value"] == 2200.0
    assert portfolio["totals"]["unrealized_pnl"] == 200.0

    sec = (await client.get("/api/hub/securities/AAPL", headers=AUTH)).json()
    assert sec["name"] == "AAPL Inc" and sec["watched"] and sec["shares_held"] == 20

    prices = (await client.get("/api/hub/securities/AAPL/prices?range=max")).json()
    assert len(prices["bars"]) == 2 and prices["stats"]["return_pct"] == 2.0
    assert prices["news_markers"] and prices["news_markers"][0]["count"] == 1

    news = (await client.get("/api/hub/securities/AAPL/news")).json()
    assert len(news["items"]) == 1
    for sort in ("recent", "impact"):
        assert (await client.get(f"/api/hub/securities/AAPL/news?sort={sort}")).status_code == 200

    dash = (await client.get("/api/hub/dashboard", headers=AUTH)).json()
    assert dash["tickers"] == ["AAPL"] and dash["movers"][0]["ticker"] == "AAPL"
    assert dash["portfolio"]["market_value"] == 2200.0 and len(dash["top_news"]) == 1

    found = (await client.get("/api/hub/search?q=aap")).json()["results"]
    assert found[0]["ticker"] == "AAPL"

    assert (await client.delete(f"/api/hub/holdings/{lot['id']}", headers=AUTH)).status_code == 200
    assert (await client.delete("/api/hub/watchlist/AAPL", headers=AUTH)).status_code == 200
    assert (await client.delete("/api/hub/watchlist/AAPL", headers=AUTH)).status_code == 404


async def test_position_reads_require_token(client: httpx.AsyncClient):
    """A public deployment must not reveal positions to anyone without the token."""
    await client.post("/api/hub/watchlist", json={"ticker": "MSFT"}, headers=AUTH)
    await client.post(
        "/api/hub/holdings", headers=AUTH, json={"ticker": "AAPL", "shares": 5, "avg_cost": 10}
    )

    assert (await client.get("/api/hub/holdings")).status_code == 401
    assert (await client.get("/api/hub/portfolio")).status_code == 401
    assert (await client.get("/api/hub/holdings", headers=AUTH)).status_code == 200

    sec = (await client.get("/api/hub/securities/AAPL")).json()
    assert sec["shares_held"] is None
    dash = (await client.get("/api/hub/dashboard")).json()
    assert dash["tickers"] == ["MSFT"] and dash["portfolio"] is None
    assert (await client.get("/api/hub/tracked")).json() == {"watchlist": ["MSFT"], "holdings": []}

    dash = (await client.get("/api/hub/dashboard", headers=AUTH)).json()
    assert dash["tickers"] == ["AAPL", "MSFT"] and dash["portfolio"] is not None


async def test_existing_feed_sees_market_news(client: httpx.AsyncClient, db: Database):
    finnhub, _ = _clients()
    async with finnhub:
        await ingest_company_news(db, finnhub, ["NVDA"])
    data = (await client.get("/api/statuses?source=market_news&ticker=NVDA")).json()
    assert data["total"] == 1 if "total" in data else len(data["items"]) == 1
    json.dumps(data)  # serializable end to end
