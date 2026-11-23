"""Non-US listings (Toronto) and multi-currency portfolios.

The failure modes worth pinning down: a ``.TO`` suffix mangled on its way to
Yahoo, a TSX symbol silently matched to a different US fund, a security listed
but never priced, and CAD and USD added together as if they were one currency.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest
from httpx import ASGITransport

from archiver.clients.market import (
    YahooChartClient,
    from_yahoo_symbol,
    is_foreign,
    parse_chart_meta,
    yahoo_symbol,
)
from archiver.hub.portfolio import Lot, summarize
from archiver.storage.db import Database
from archiver.storage.models import Holding, Security
from archiver.web import create_app

AUTH = {"X-Hub-Token": "secret"}


# ── symbols ───────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("ours", "yahoo"),
    [("BRK.B", "BRK-B"), ("VFV.TO", "VFV.TO"), ("BBD.B.TO", "BBD-B.TO"), ("AAPL", "AAPL")],
)
def test_yahoo_symbol_round_trip(ours: str, yahoo: str):
    assert yahoo_symbol(ours) == yahoo
    assert from_yahoo_symbol(yahoo) == ours


def test_is_foreign():
    assert is_foreign("VFV.TO") and is_foreign("xdiv.to") and is_foreign("ABC.V")
    assert not is_foreign("BRK.B") and not is_foreign("XDIV")


def _meta(**over) -> dict:
    meta = {
        "currency": "CAD",
        "symbol": "VFV.TO",
        "fullExchangeName": "Toronto",
        "instrumentType": "ETF",
        "regularMarketTime": 1795467586,
        "regularMarketPrice": 184.72,
        "regularMarketDayHigh": 185.92,
        "regularMarketDayLow": 182.23,
        "longName": "Vanguard S&P 500 Index ETF",
        "chartPreviousClose": 176.29,
        **over,
    }
    return {"chart": {"result": [{"meta": meta}], "error": None}}


def test_chart_meta_gives_profile_currency_and_day_change():
    snap = parse_chart_meta(_meta())
    assert snap["name"] == "Vanguard S&P 500 Index ETF"
    assert snap["currency"] == "CAD" and snap["exchange"] == "Toronto"
    assert snap["security_type"] == "ETP"
    assert snap["change"] == pytest.approx(8.43)
    assert snap["pct_change"] == pytest.approx(4.782, abs=1e-3)


def test_chart_meta_for_unknown_symbol_is_none():
    assert parse_chart_meta({"chart": {"result": None, "error": {"code": "Not Found"}}}) is None


# ── currency ──────────────────────────────────────────────────────────────────
def test_totals_convert_to_base_and_positions_keep_their_own_currency():
    out = summarize(
        [Lot("VFV.TO", 10, 180.0), Lot("AAPL", 10, 100.0)],
        {
            "VFV.TO": {"price": 200.0, "change": 2.0, "currency": "CAD"},
            "AAPL": {"price": 110.0, "change": 1.0, "currency": "USD"},
        },
        base="CAD",
        fx={"USD": 1.40},
    )
    by = {p["ticker"]: p for p in out["positions"]}
    # Native figures stay native...
    assert by["AAPL"]["currency"] == "USD" and by["AAPL"]["market_value"] == 1100.0
    # ...and are converted for the totals and weights.
    assert by["AAPL"]["market_value_base"] == 1540.0
    t = out["totals"]
    assert t["currency"] == "CAD"
    assert t["market_value"] == 2000.0 + 1540.0
    assert t["cost_basis"] == 1800.0 + 1400.0
    assert t["unrealized_pnl"] == 200.0 + 140.0
    assert t["day_change"] == 20.0 + 14.0
    assert by["VFV.TO"]["weight_pct"] == pytest.approx(2000 / 3540 * 100, abs=0.01)
    assert out["fx"] == {"USD": 1.4}


def test_currency_without_a_rate_is_flagged_never_guessed():
    out = summarize(
        [Lot("VFV.TO", 10, 180.0), Lot("AAPL", 10, 100.0)],
        {
            "VFV.TO": {"price": 200.0, "change": 2.0, "currency": "CAD"},
            "AAPL": {"price": 110.0, "change": 1.0, "currency": "USD"},
        },
        base="CAD",
        fx={},
    )
    assert out["unconverted"] == ["AAPL"]
    assert out["totals"]["market_value"] == 2000.0  # AAPL left out, not added 1:1


# ── API ───────────────────────────────────────────────────────────────────────
@pytest.fixture
async def client(db: Database, monkeypatch) -> AsyncIterator[httpx.AsyncClient]:
    monkeypatch.setenv("FINNHUB_API_KEY", "")
    monkeypatch.setenv("HUB_WRITE_TOKEN", "secret")
    monkeypatch.setenv("PORTFOLIO_CURRENCY", "CAD")
    from archiver.config import settings as settings_mod

    settings_mod.get_settings.cache_clear()

    listings = {
        "VFV.TO": parse_chart_meta(_meta()),
        "TD.TO": parse_chart_meta(
            _meta(symbol="TD.TO", longName="The Toronto-Dominion Bank", instrumentType="EQUITY")
        ),
    }
    calls: list[str] = []

    async def snapshot(self, ticker):
        calls.append(ticker)
        return listings.get(ticker)

    async def fx_rate(self, a, b):
        return {("USD", "CAD"): 1.40}.get((a, b))

    async def daily_bars(self, ticker, *, range_="5y"):
        return []

    monkeypatch.setattr(YahooChartClient, "snapshot", snapshot)
    monkeypatch.setattr(YahooChartClient, "fx_rate", fx_rate)
    monkeypatch.setattr(YahooChartClient, "daily_bars", daily_bars)

    async with db.session() as session, session.begin():
        # The weekly universe sync lists US symbols without pricing them.
        session.add(Security(ticker="TD", name="Toronto-Dominion Bank", currency="USD"))
        session.add(
            Security(
                ticker="AAPL",
                name="Apple",
                currency="USD",
                price=110.0,
                change=1.0,
                quote_at=datetime.now(UTC),
            )
        )
    transport = ASGITransport(app=create_app(db))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        c.calls = calls  # type: ignore[attr-defined]
        yield c


async def test_toronto_listing_fills_in_on_first_visit(client: httpx.AsyncClient):
    body = (await client.get("/api/hub/securities/VFV.TO")).json()
    assert body["name"] == "Vanguard S&P 500 Index ETF"
    assert body["currency"] == "CAD"
    assert body["quote"]["price"] == 184.72


async def test_search_finds_both_td_lines_us_first(client: httpx.AsyncClient):
    found = [r["ticker"] for r in (await client.get("/api/hub/search?q=TD")).json()["results"]]
    assert found[:2] == ["TD", "TD.TO"]


async def test_search_finds_toronto_only_symbol(client: httpx.AsyncClient):
    found = (await client.get("/api/hub/search?q=vfv")).json()["results"]
    assert found[0]["ticker"] == "VFV.TO"
    assert "Toronto" in found[0]["name"]


async def test_portfolio_mixes_cad_and_usd_correctly(client: httpx.AsyncClient, db: Database):
    await client.get("/api/hub/securities/VFV.TO")  # prices it
    async with db.session() as session, session.begin():
        session.add(Holding(ticker="VFV.TO", shares=10, avg_cost=180.0))
        session.add(Holding(ticker="AAPL", shares=10, avg_cost=100.0))
    port = (await client.get("/api/hub/portfolio", headers=AUTH)).json()
    assert port["totals"]["currency"] == "CAD"
    assert port["fx"] == {"USD": 1.4}
    assert port["totals"]["market_value"] == pytest.approx(1847.2 + 1540.0)
    assert port["unconverted"] == [] and port["unpriced"] == []


async def test_stored_toronto_symbol_ranks_above_prefix_matches(
    client: httpx.AsyncClient, db: Database
):
    async with db.session() as session, session.begin():
        session.add(Security(ticker="VFVA", name="Vanguard U.S. Value Factor", currency="USD"))
        session.add(Security(ticker="VFV.TO", name="Vanguard S&P 500 Index ETF", currency="CAD"))
    found = [r["ticker"] for r in (await client.get("/api/hub/search?q=VFV")).json()["results"]]
    assert found[:2] == ["VFV.TO", "VFVA"]


async def test_us_listing_stays_usd_when_profile_names_home_market(db: Database, monkeypatch):
    """Finnhub's profile for TD says Toronto/CAD; its free quote is the NYSE line in USD."""
    from archiver.clients.market import FinnhubClient, Quote
    from archiver.hub.service import refresh_security

    async def quote(self, t):
        return Quote(115.68, 1.0, 0.9, None, None, None, 114.68, datetime.now(UTC))

    async def profile(self, t):
        return {
            "name": "Toronto-Dominion Bank",
            "exchange": "TORONTO STOCK EXCHANGE",
            "currency": "CAD",
        }

    async def nothing(self, t):
        return {}

    monkeypatch.setattr(FinnhubClient, "quote", quote)
    monkeypatch.setattr(FinnhubClient, "profile", profile)
    monkeypatch.setattr(FinnhubClient, "metrics", nothing)
    monkeypatch.setattr(FinnhubClient, "recommendation", nothing)
    async with db.session() as session, session.begin():
        session.add(
            Security(ticker="TD", name="Toronto-Dominion Bank", exchange="XNYS", currency="USD")
        )

    async with FinnhubClient(api_key="k", user_agent="test") as fh:
        await refresh_security(db, fh, "TD")
    async with db.session() as session:
        td = await session.get(Security, "TD")
    assert (td.currency, td.exchange, td.price) == ("USD", "XNYS", 115.68)
