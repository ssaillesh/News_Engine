"""Tests for the Polymarket × coverage page.

The cases that matter are the accuracy ones: a market's YES side read by name,
long shots kept out of a market's signature, links that need something specific
in common, ET day boundaries, and statistics withheld when the sample is thin.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from httpx import ASGITransport

from archiver.clients.market import PolymarketClient, PolymarketHistoryClient
from archiver.hub import polymarket as pm
from archiver.reference.people import find_people
from archiver.storage.db import Database
from archiver.storage.repositories import (
    AccountRepository,
    StatusRepository,
    StatusSentimentRepository,
)
from archiver.web import create_app


def _market(mid: str, question: str, p: float, **extra) -> dict:
    return {
        "id": mid,
        "question": question,
        "outcomes": json.dumps(["Yes", "No"]),
        "outcomePrices": json.dumps([str(p), str(round(1 - p, 4))]),
        "clobTokenIds": json.dumps([f"yes-{mid}", f"no-{mid}"]),
        "oneDayPriceChange": 0.02,
        "volume24hr": 1000,
        **extra,
    }


def _event(eid: str, title: str, markets: list[dict], tags: tuple[str, ...] = ()) -> dict:
    return {
        "id": eid,
        "slug": f"slug-{eid}",
        "title": title,
        "volume24hr": 5000,
        "markets": markets,
        "tags": [{"slug": t} for t in tags],
    }


# ── people lexicon ────────────────────────────────────────────────────────────
def test_people_match_possessives_and_full_names():
    assert find_people("Putin's envoy meets Zelenskyy") == {
        "PUTIN": "Putin",
        "ZELENSKY": "Zelenskyy",
    }
    assert find_people("Kim Jong Un fires missile") == {"KIMJU": "Kim Jong Un"}


def test_risky_bare_names_do_not_match():
    # Common surnames and lower-case words must not become world leaders.
    assert find_people("Kim and Lee met Johnson and Harris at the deli") == {}
    assert find_people("a musk-scented candle and xi characters") == {}


# ── parsing ───────────────────────────────────────────────────────────────────
def test_yes_side_is_found_by_name_not_position():
    m = _market("1", "Will X happen?", 0.3)
    m["outcomes"] = json.dumps(["No", "Yes"])
    m["outcomePrices"] = json.dumps(["0.7", "0.3"])
    m["clobTokenIds"] = json.dumps(["no-tok", "yes-tok"])
    out = pm.parse_outcome(m)
    assert out["probability"] == 30.0
    assert out["token"] == "yes-tok"


def test_closed_and_non_binary_markets_are_skipped():
    assert pm.parse_outcome(_market("1", "q", 0.5, closed=True)) is None
    weird = _market("2", "q", 0.5)
    weird["outcomes"] = json.dumps(["Up", "Down"])
    assert pm.parse_outcome(weird) is None


def test_event_with_only_decided_outcomes_is_dropped():
    ev = _event("9", "Done deal?", [_market("1", "Done?", 0.999)])
    assert pm.parse_event(ev) is None


def test_long_shot_outcomes_stay_out_of_the_signature():
    ev = pm.parse_event(
        _event(
            "1",
            "Republican Presidential Nominee 2028",
            [
                _market("1", "Will JD Vance win the nomination?", 0.33),
                _market("2", "Will Elon Musk win the nomination?", 0.003),
            ],
        )
    )
    assert "person:VANCE" in ev.keys
    assert "person:MUSK" not in ev.keys  # a 0.3% long shot must not pull in Musk's news


def test_themes_come_from_tags_and_people():
    ev = pm.parse_event(
        _event(
            "1",
            "Netanyahu out by...?",
            [_market("1", "Netanyahu out by June?", 0.2)],
            ("geopolitics", "trump"),
        )
    )
    assert ev.themes == ["conflict", "leaders"]  # "trump" is fetched but never themed


# ── linking ───────────────────────────────────────────────────────────────────
def test_topic_alone_never_links():
    market = pm.signature("Will tariffs on steel rise?")
    headline = pm.signature("Tariffs hit consumers again")
    assert pm.link(market, headline) is None


def test_two_country_market_needs_more_than_one_country():
    market = pm.signature("Will China invade Taiwan by 2027?")
    assert pm.link(market, pm.signature("China cuts interest rates")) is None
    why = pm.link(market, pm.signature("China sends warships toward Taiwan"))
    assert {k.label for k in why} == {"China", "Taiwan"}


def test_single_subject_market_links_on_that_subject():
    market = pm.signature("Will the U.S. invade Iran before 2027?")
    why = pm.link(market, pm.signature("Trump weighs new options on Iran"))
    assert [k.label for k in why] == ["Iran"]


def test_fed_bare_word_matches_market_wording():
    market = pm.signature("Will the Fed decrease interest rates by 25 bps?")
    assert pm.link(market, pm.signature("Fed holds rates steady")) is not None


# ── series & statistics ───────────────────────────────────────────────────────
def test_daily_closes_use_eastern_days():
    # 03:00 UTC on the 23rd is still the evening of the 22nd in New York.
    closes = pm.daily_closes(
        [
            (datetime(2026, 11, 22, 20, 0, tzinfo=UTC), 0.40),
            (datetime(2026, 11, 23, 3, 0, tzinfo=UTC), 0.45),
            (datetime(2026, 11, 23, 18, 0, tzinfo=UTC), 0.60),
        ]
    )
    assert closes == {date(2026, 11, 22): 45.0, date(2026, 11, 23): 60.0}


def test_build_days_changes_from_previous_close_including_before_the_window():
    closes = {date(2026, 11, 1): 40.0, date(2026, 11, 3): 50.0, date(2026, 11, 5): 47.0}
    days = pm.build_days(closes, [], start=date(2026, 11, 3), end=date(2026, 11, 5))
    assert [(d["probability"], d["change"]) for d in days] == [
        (50.0, 10.0),  # against Nov 1, the last close before the window
        (None, None),  # no trade that day: no close, no change
        (47.0, -3.0),  # against the last close, not the missing day
    ]


def test_pearson_known_values():
    assert pm.pearson([1, 2, 3, 4], [2, 4, 6, 8]) == pytest.approx(1.0)
    assert pm.pearson([1, 2, 3, 4], [8, 6, 4, 2]) == pytest.approx(-1.0)
    assert pm.pearson([1, 1, 1], [1, 2, 3]) is None  # flat: undefined, not zero


def test_correlation_is_withheld_below_min_days():
    days = [
        {"change": float(i), "sentiment": float(i) / 10, "news_count": i}
        for i in range(pm.MIN_DAYS - 1)
    ]
    stats = pm.correlation_stats(days)
    assert stats["co_movement"] == {"r": None, "n": pm.MIN_DAYS - 1, "strength": "insufficient"}


def test_correlation_reported_with_its_sample_size():
    days = [{"change": float(i), "sentiment": float(i), "news_count": i} for i in range(10)]
    stats = pm.correlation_stats(days)
    assert stats["co_movement"]["r"] == pytest.approx(1.0)
    assert stats["co_movement"]["n"] == 10
    assert stats["co_movement"]["strength"] == "strong"


# ── API ───────────────────────────────────────────────────────────────────────
@pytest.fixture
async def client(db: Database, monkeypatch) -> AsyncIterator[httpx.AsyncClient]:
    from archiver.config import settings as settings_mod

    settings_mod.get_settings.cache_clear()

    iran = _event(
        "100",
        "Will the U.S. invade Iran before 2027?",
        [_market("1001", "Will the U.S. invade Iran before 2027?", 0.055)],
        ("geopolitics",),
    )

    async def events(self, tag, *, limit=12):
        return [iran] if tag == "geopolitics" else []

    async def history(self, token, **_kw):
        now = datetime.now(UTC)
        return [(now - timedelta(days=d), 0.05 + d / 1000) for d in range(10, -1, -1)]

    monkeypatch.setattr(PolymarketClient, "events", events)
    monkeypatch.setattr(PolymarketHistoryClient, "history", history)

    async with db.session() as session, session.begin():
        await AccountRepository(session, db.dialect).upsert({"id": "news:acct", "username": "n"})
        repo = StatusRepository(session, db.dialect)
        for sid, text in [
            ("news:1", "Trump weighs new options on Iran"),
            ("news:2", "Stocks rally on chip news"),
        ]:
            await repo.upsert(
                {
                    "id": sid,
                    "account_id": "news:acct",
                    "created_at": datetime.now(UTC) - timedelta(hours=2),
                    "content_text": text,
                    "content_hash": sid,
                    "source": "news",
                    "kind": "Reuters",
                }
            )
        await StatusSentimentRepository(session, db.dialect).upsert(
            {
                "status_id": "news:1",
                "model": "m",
                "label": "negative",
                "score": 0.8,
                "positive": 0.1,
                "negative": 0.8,
                "neutral": 0.1,
                "compound": -0.7,
                "scored_content_hash": "news:1",
            }
        )

    transport = ASGITransport(app=create_app(db))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_list_links_coverage_with_reasons(client: httpx.AsyncClient):
    body = (await client.get("/api/hub/polymarket")).json()
    assert [i["id"] for i in body["items"]] == ["100"]
    item = body["items"][0]
    assert item["lead"]["probability"] == 5.5
    assert item["coverage"]["count_7d"] == 1  # the chip story does not link
    assert item["coverage"]["avg_sentiment_7d"] == pytest.approx(-0.7)
    assert [k["label"] for k in item["coverage"]["latest"]["why"]] == ["Iran"]
    assert {t["key"]: t["count"] for t in body["themes"]}["conflict"] == 1


async def test_detail_sets_odds_beside_coverage(client: httpx.AsyncClient):
    body = (await client.get("/api/hub/polymarket/100")).json()
    assert body["outcome"]["id"] == "1001"
    assert len(body["days"]) == pm.WINDOW_DAYS
    today = body["days"][-1]
    assert today["probability"] == pytest.approx(5.0)
    assert today["news_count"] == 1
    assert [h["id"] for h in body["headlines"]] == ["news:1"]
    assert body["stats"]["co_movement"]["strength"] == "insufficient"  # one day of overlap


async def test_unknown_theme_is_just_empty(client: httpx.AsyncClient):
    body = (await client.get("/api/hub/polymarket?theme=sports")).json()
    assert body["items"] == []
