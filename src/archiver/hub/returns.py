"""Price-move math over stored daily bars: period returns and reactions to news.

Everything here is pure (closes in, numbers out) except :func:`load_closes`, so
the rules about which bar a story "lands on" are tested without a database.

A story's *session* is the first trading day whose close can reflect it: the
day it was published if that was before the 4pm ET close, else the next one.
Date-only timestamps (Federal Register, presidential documents) are stored as
midnight UTC, which is the evening before in New York, so they land on the
morning of their own date, which is when they are published.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime, time, timedelta, timezone, tzinfo
from typing import TYPE_CHECKING

from sqlalchemy import select

from archiver.storage.models import PriceBar, Security

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

Closes = Sequence[tuple[date, float]]  # ascending by date

MARKET_CLOSE = time(16, 0)


def _eastern() -> tzinfo:
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo("America/New_York")
    except Exception:  # no tz database on the host: EST is close enough for a session cut
        return timezone(timedelta(hours=-5))


ET = _eastern()


def pct(new: float | None, old: float | None) -> float | None:
    if new is None or not old:
        return None
    return round((new / old - 1) * 100, 4)


def session_date(at: datetime) -> tuple[date, bool]:
    """The calendar day a story can first move prices, and whether that day is
    *after* it (published after the close, so the next trading day counts)."""
    local = (at if at.tzinfo else at.replace(tzinfo=UTC)).astimezone(ET)
    return local.date(), local.time() >= MARKET_CLOSE


def period_returns(closes: Closes) -> dict[str, float | date | None]:
    """Last close plus 1-day, 5-day, 1-month and year-to-date returns, in percent."""
    if not closes:
        return {"date": None, "close": None, "r1d": None, "r5d": None, "r1m": None, "rytd": None}
    dates = [d for d, _ in closes]
    last_day, last = closes[-1]

    def back(n: int) -> float | None:
        return closes[-1 - n][1] if len(closes) > n else None

    def on_or_before(day: date) -> float | None:
        i = bisect_right(dates, day)
        return closes[i - 1][1] if i else None

    return {
        "date": last_day,
        "close": last,
        "r1d": pct(last, back(1)),
        "r5d": pct(last, back(5)),
        "r1m": pct(last, on_or_before(last_day - timedelta(days=30))),
        "rytd": pct(last, on_or_before(date(last_day.year - 1, 12, 31))),
    }


def reaction(closes: Closes, at: datetime, horizon: int = 5) -> dict[str, float | date | None]:
    """Move from the close before a story's session to the session close (``d1``)
    and to the close ``horizon`` sessions in (``d5``), in percent."""
    empty: dict[str, float | date | None] = {"session": None, "d1": None, "d5": None}
    if not closes:
        return empty
    dates = [d for d, _ in closes]
    day, after_close = session_date(at)
    i = bisect_right(dates, day) if after_close else bisect_left(dates, day)
    if i == 0 or i >= len(closes):  # no prior close to measure from, or no session yet
        return empty
    base = closes[i - 1][1]
    end = i + horizon - 1
    return {
        "session": closes[i][0],
        "d1": pct(closes[i][1], base),
        "d5": pct(closes[end][1], base) if end < len(closes) else None,
    }


async def load_closes(
    session: AsyncSession, tickers: Iterable[str], start: date
) -> dict[str, list[tuple[date, float]]]:
    """Ascending (date, close) per ticker from ``start`` on; tickers with no bars are absent."""
    wanted = sorted(set(tickers))
    out: dict[str, list[tuple[date, float]]] = {}
    if not wanted:
        return out
    rows = await session.execute(
        select(PriceBar.ticker, PriceBar.date, PriceBar.close)
        .where(PriceBar.ticker.in_(wanted), PriceBar.date >= start, PriceBar.close.is_not(None))
        .order_by(PriceBar.ticker, PriceBar.date)
    )
    for ticker, day, close in rows.all():
        out.setdefault(ticker, []).append((day, close))
    return out


async def overlay_quotes(
    session: AsyncSession, closes: dict[str, list[tuple[date, float]]]
) -> date | None:
    """Extend each ticker's daily closes with its live quote when that is newer.

    A quote stamped on a day with no bar yet is appended as that day's close
    (so far); one on the last bar's day replaces it. Returns the latest day a
    quote supplied, or None when every series was already up to date.
    """
    if not closes:
        return None
    rows = await session.execute(
        select(Security.ticker, Security.price, Security.quote_at).where(
            Security.ticker.in_(list(closes)), Security.price.is_not(None)
        )
    )
    latest: date | None = None
    for ticker, price, at in rows.all():
        series = closes.get(ticker)
        if not series or at is None:
            continue
        day = (at if at.tzinfo else at.replace(tzinfo=UTC)).astimezone(ET).date()
        last_day, last_close = series[-1]
        if day > last_day:
            series.append((day, price))
        elif day == last_day and price != last_close:
            series[-1] = (day, price)
        else:
            continue
        latest = max(latest or day, day)
    return latest
