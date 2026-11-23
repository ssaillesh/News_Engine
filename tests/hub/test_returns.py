"""Price-move math, Polymarket odds selection, and the endpoints built on them.

No network: Polymarket is faked by patching the client.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from httpx import ASGITransport

from archiver.hub.odds import pick_odds
from archiver.hub.returns import period_returns, reaction, session_date
from archiver.storage.db import Database
from archiver.storage.models import PriceBar, Security, Status, StockMention
from archiver.web import create_app

# Mon 2 Nov .. Fri 13 Nov 2026, ten sessions, closing at 100, 101, ... 109.
DAYS = [date(2026, 11, 2) + timedelta(days=i) for i in range(12) if (2 + i) % 7 not in (0, 1)]
CLOSES = [(d, 100.0 + i) for i, d in enumerate(DAYS)]


def test_period_returns():
    r = period_returns(CLOSES)
    assert r["date"] == date(2026, 11, 13) and r["close"] == 109.0
    assert r["r1d"] == pytest.approx((109 / 108 - 1) * 100, abs=1e-3)
    assert r["r5d"] == pytest.approx((109 / 104 - 1) * 100, abs=1e-3)
    assert r["r1m"] is None and r["rytd"] is None  # not enough history
    assert period_returns([])["close"] is None


def test_session_date_cuts_at_the_close():
    # 15:59 ET counts for the same day; 16:00 ET waits for the next one.
    assert session_date(datetime(2026, 11, 4, 20, 59, tzinfo=UTC)) == (date(2026, 11, 4), False)
    assert session_date(datetime(2026, 11, 4, 21, 0, tzinfo=UTC)) == (date(2026, 11, 4), True)
    # Date-only documents (midnight UTC) are the evening before in New York.
    assert session_date(datetime(2026, 11, 4, tzinfo=UTC)) == (date(2026, 11, 3), True)


def test_reaction():
    # Wednesday mid-session: lands on Wednesday (close 102) from Tuesday's 101.
    r = reaction(CLOSES, datetime(2026, 11, 4, 15, tzinfo=UTC))
    assert r["session"] == date(2026, 11, 4)
    assert r["d1"] == pytest.approx((102 / 101 - 1) * 100, abs=1e-3)
    assert r["d5"] == pytest.approx((106 / 101 - 1) * 100, abs=1e-3)
    # Saturday news lands on Monday.
    assert reaction(CLOSES, datetime(2026, 11, 7, 15, tzinfo=UTC))["session"] == date(2026, 11, 9)
    # Too late for five sessions, too early for a prior close, or no session yet.
    assert reaction(CLOSES, datetime(2026, 11, 12, 15, tzinfo=UTC))["d5"] is None
    assert reaction(CLOSES, datetime(2026, 11, 2, 15, tzinfo=UTC))["session"] is None
    assert reaction(CLOSES, datetime(2026, 11, 14, 15, tzinfo=UTC))["session"] is None


def _market(mid: str, p: float, vol: float, **extra) -> dict:
    return {"id": mid, "question": f"Q{mid}?", "outcomePrices": json.dumps([str(p), str(1 - p)]),
            "volume24hr": vol, "oneDayPriceChange": 0.04, **extra}  # fmt: skip


def test_pick_odds_keeps_open_uncertain_busy_markets():
    events = [
        {"slug": "fed", "markets": [_market("1", 0.5, 10), _market("2", 0.995, 99)]},
        {"slug": "tariffs", "markets": [_market("3", 0.3, 50), _market("4", 0.4, 70, closed=True)]},
        {"slug": "dup", "markets": [_market("1", 0.5, 10), {"id": "5", "outcomePrices": "junk"}]},
    ]
    rows = pick_odds(events)
    assert [r["question"] for r in rows] == ["Q3?", "Q1?"]
    assert rows[0]["probability"] == 30.0 and rows[0]["change_1d"] == 4.0
    assert rows[0]["url"] == "https://polymarket.com/event/tariffs"


# ── API ──────────────────────────────────────────────────────────────────────
@pytest.fixture
async def client(db: Database, monkeypatch) -> AsyncIterator[httpx.AsyncClient]:
    monkeypatch.setenv("FINNHUB_API_KEY", "")
    monkeypatch.setenv("HUB_WRITE_TOKEN", "")
    from archiver.config import settings as settings_mod

    settings_mod.get_settings.cache_clear()
    transport = ASGITransport(app=create_app(db))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _seed(db: Database) -> None:
    async with db.session() as session, session.begin():
        session.add_all(
            [
                Security(
                    ticker="NVDA",
                    name="Nvidia",
                    is_core=True,
                    security_type="Common Stock",
                    sector="Information Technology",
                    price=109.0,
                    pct_change=0.9,
                    metrics={"peTTM": 38.1},
                ),  # fmt: skip
                Security(
                    ticker="SPY",
                    name="S&P 500 ETF",
                    is_core=True,
                    security_type="ETP",
                    sector="ETF",
                    price=54.5,
                    pct_change=0.1,
                ),  # fmt: skip
            ]
        )
        for d, c in CLOSES:
            session.add(PriceBar(ticker="NVDA", date=d, close=c))
            session.add(PriceBar(ticker="SPY", date=d, close=c / 2))


async def test_returns_and_reactions_endpoints(client: httpx.AsyncClient, db: Database):
    await _seed(db)
    data = (await client.get("/api/hub/returns?tickers=nvda,SPY,ZZZZ")).json()["items"]
    assert data["NVDA"]["date"] == "2026-11-13" and data["NVDA"]["r5d"] > 4.8
    assert data["ZZZZ"]["close"] is None

    at = "2026-11-04T15:00:00Z"
    out = (await client.get(f"/api/hub/reactions?at={at}&tickers=NVDA")).json()
    assert out["benchmark"] == "SPY"
    ev = out["events"][0]
    assert ev["session"] == "2026-11-04"
    assert ev["moves"]["NVDA"]["d1"] == pytest.approx(ev["moves"]["SPY"]["d1"])
    assert (
        await client.get("/api/hub/returns?tickers=" + ",".join(f"T{i}" for i in range(101)))
    ).status_code == 422


async def test_securities_filters_and_extras(client: httpx.AsyncClient, db: Database):
    await _seed(db)
    stocks = (await client.get("/api/hub/securities?kind=stock")).json()
    assert [r["ticker"] for r in stocks["items"]] == ["NVDA"]
    row = stocks["items"][0]
    assert row["pe"] == 38.1 and row["r5d"] is not None and row["news_7d"] == 0
    etfs = (await client.get("/api/hub/securities?kind=etf")).json()
    assert [r["ticker"] for r in etfs["items"]] == ["SPY"]
    both = (await client.get("/api/hub/securities?scope=all&tickers=SPY,NVDA")).json()
    assert both["total"] == 2
    sec = (await client.get("/api/hub/securities/NVDA")).json()
    assert sec["sector"] == "Information Technology" and sec["security_type"] == "Common Stock"


async def test_statuses_accepts_lists_and_total(client: httpx.AsyncClient, db: Database):
    from archiver.storage.models import Account

    now = datetime.now(UTC)
    async with db.session() as session, session.begin():
        session.add(Account(id="a", username="a"))
        for i, (src, kind, tick) in enumerate(
            [
                ("whitehouse", "Fact Sheets", "NVDA"),
                ("federal_register", "Executive Order", "AAPL"),
                ("news", "Reuters", None),
            ]  # fmt: skip
        ):
            when = now - timedelta(hours=i)
            session.add(Status(id=f"s{i}", account_id="a", created_at=when, content_hash=f"h{i}",
                               content_text=f"t{i}", source=src, kind=kind))  # fmt: skip
            if tick:
                session.add(StockMention(status_id=f"s{i}", ticker=tick))
    data = (
        await client.get("/api/statuses?source=whitehouse,federal_register&with_total=true")
    ).json()
    assert data["total"] == 2 and {i["source"] for i in data["items"]} == {
        "whitehouse",
        "federal_register",
    }
    assert len((await client.get("/api/statuses?ticker=nvda,AAPL")).json()["items"]) == 2
    assert (
        len((await client.get("/api/statuses?kind=Executive Order,Reuters")).json()["items"]) == 2
    )
    assert "total" not in (await client.get("/api/statuses")).json()
    picked = (await client.get("/api/statuses?id=s2,s0")).json()["items"]
    assert sorted(i["id"] for i in picked) == ["s0", "s2"]


async def test_odds_endpoint_caches_and_survives_outage(
    client: httpx.AsyncClient, db: Database, monkeypatch
):
    from archiver.clients.exceptions import ClientError
    from archiver.clients.market import PolymarketClient

    calls = {"n": 0}

    async def fake_events(self, tag: str, *, limit: int = 12):
        calls["n"] += 1
        return [{"slug": tag, "markets": [_market(tag, 0.4, 5)]}]

    monkeypatch.setattr(PolymarketClient, "events", fake_events)
    first = (await client.get("/api/hub/odds")).json()
    assert first["source"] == "polymarket" and len(first["items"]) == 3
    n = calls["n"]
    assert len((await client.get("/api/hub/odds?limit=1")).json()["items"]) == 1
    assert calls["n"] == n  # served from the cache

    async def broken(self, tag: str, *, limit: int = 12):
        raise ClientError("down")

    # A fresh app has an empty cache, so an outage degrades to an empty list.
    monkeypatch.setattr(PolymarketClient, "events", broken)
    transport = ASGITransport(app=create_app(db))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as fresh:
        out = (await fresh.get("/api/hub/odds")).json()
    assert out["items"] == [] and out["error"]
