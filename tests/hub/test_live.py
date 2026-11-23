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
