from datetime import UTC, date, datetime

from archiver.hub.live import market_open, plan


def test_market_open_regular_session_only():
    # Mon 23 Nov 2026: 15:00 UTC = 10:00 ET (open), 14:00 UTC = 09:00 ET (pre-market)
    assert market_open(datetime(2026, 11, 23, 15, 0, tzinfo=UTC))
    assert not market_open(datetime(2026, 11, 23, 14, 0, tzinfo=UTC))
    assert not market_open(datetime(2026, 11, 23, 21, 0, tzinfo=UTC))  # 16:00 ET close
    assert not market_open(datetime(2026, 11, 22, 16, 0, tzinfo=UTC))  # Sunday


def test_plan_puts_priority_first_and_respects_budget():
    assert plan(["SPY", "AAPL", "SPY"], ["MSFT", "AAPL", "NVDA"], 4) == [
        "SPY",
        "AAPL",
        "MSFT",
        "NVDA",
    ]
    assert plan(["SPY", "QQQ"], ["A", "B"], 1) == ["SPY"]


async def test_overlay_appends_and_replaces(tmp_path):
    from archiver.hub.returns import overlay_quotes
    from archiver.storage.db import Database
    from archiver.storage.models import Security

    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'x.db'}")
    await db.create_all()
    async with db.session() as s, s.begin():
        s.add(
            Security(ticker="SPY", price=700.0, quote_at=datetime(2026, 11, 23, 16, 0, tzinfo=UTC))
        )
        s.add(
            Security(ticker="QQQ", price=500.0, quote_at=datetime(2026, 11, 20, 20, 0, tzinfo=UTC))
        )
        s.add(
            Security(ticker="IWM", price=None, quote_at=datetime(2026, 11, 23, 16, 0, tzinfo=UTC))
        )
    closes = {
        "SPY": [(date(2026, 11, 19), 710.0), (date(2026, 11, 20), 689.8)],
        "QQQ": [(date(2026, 11, 20), 498.0)],
        "IWM": [(date(2026, 11, 20), 200.0)],
    }
    async with db.session() as s:
        latest = await overlay_quotes(s, closes)
    assert closes["SPY"][-1] == (date(2026, 11, 23), 700.0)  # new session appended
    assert closes["QQQ"] == [(date(2026, 11, 20), 500.0)]  # same day: replaced
    assert closes["IWM"] == [(date(2026, 11, 20), 200.0)]  # no price: untouched
    assert latest == date(2026, 11, 23)
    await db.dispose()


def test_parse_spark_maps_share_classes_and_skips_empty():
    from archiver.clients.market import parse_spark

    out = parse_spark(
        {
            "BE": {
                "timestamp": [1795449315],
                "close": [170.925],
                "chartPreviousClose": 142.39,
                "fulldayPrice": 170.925,
                "fulldayChange": 28.535,
                "fulldayChangePercent": 20.04,
            },
            "BRK-B": {"timestamp": [1795449315], "close": [500.0], "chartPreviousClose": 400.0},
            "NOPE": {"timestamp": [], "close": []},
        }
    )
    assert set(out) == {"BE", "BRK.B"}
    assert out["BE"].pct_change == 20.04 and out["BE"].prev_close == 142.39
    assert out["BRK.B"].pct_change == 25.0 and out["BRK.B"].day_high is None


async def test_write_quotes_skips_older_and_clears_stale_range(tmp_path):
    from archiver.clients.market import Quote
    from archiver.hub.live import write_quotes
    from archiver.storage.db import Database
    from archiver.storage.models import Security

    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'x.db'}")
    await db.create_all()
    fri = datetime(2026, 11, 20, 21, 0, tzinfo=UTC)
    mon = datetime(2026, 11, 23, 15, 0, tzinfo=UTC)
    async with db.session() as s, s.begin():
        s.add(Security(ticker="BE", price=142.39, pct_change=-15.3, day_high=163.5, quote_at=fri))
        s.add(Security(ticker="SPY", price=725.0, quote_at=mon))
    q = lambda p, pct, at: Quote(p, None, pct, None, None, None, None, at)  # noqa: E731
    n = await write_quotes(
        db, {"BE": q(170.9, 20.04, mon), "SPY": q(700.0, 1.0, fri), "ZZZ": q(1.0, 1.0, mon)}
    )
    assert n == 1  # SPY's quote is older than the stored one; ZZZ has no row
    async with db.session() as s:
        be = await s.get(Security, "BE")
        spy = await s.get(Security, "SPY")
    assert be.pct_change == 20.04 and be.day_high is None  # Friday's range cleared
    assert spy.price == 725.0
    await db.dispose()
