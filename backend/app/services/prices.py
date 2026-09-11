"""Persistence for securities and price bars.

Upserts, so a re-run of a backfill is idempotent: the last trading day of a
previous run is refetched and overwritten rather than duplicated.
"""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Price, Security
from app.services.yahoo import PriceBar, SecurityProfile

# Postgres caps a statement at 65535 bound parameters; 7 columns per row leaves
# ample headroom at this size, and ~10 years of daily bars is only ~2500 rows.
_CHUNK = 2000


def upsert_security(session: Session, profile: SecurityProfile) -> None:
    """Insert the security, refreshing descriptive fields if it already exists."""
    stmt = insert(Security).values(
        ticker=profile.ticker,
        name=profile.name,
        exchange=profile.exchange,
        sector=profile.sector,
        market_cap=profile.market_cap,
    )
    # COALESCE so a flaky .info call returning nothing cannot blank out fields a
    # previous, successful run stored: the new value wins unless it is NULL.
    refreshed = {
        column: func.coalesce(stmt.excluded[column], getattr(Security, column))
        for column in ("name", "exchange", "sector", "market_cap")
    }
    session.execute(
        stmt.on_conflict_do_update(index_elements=[Security.ticker], set_=refreshed)
    )


def upsert_prices(session: Session, ticker: str, bars: list[PriceBar]) -> int:
    """Write bars for ``ticker``. Returns the number of rows sent."""
    if not bars:
        return 0

    rows = [
        {
            "ticker": ticker,
            "date": bar.date,
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
        }
        for bar in bars
    ]

    for start in range(0, len(rows), _CHUNK):
        chunk = rows[start : start + _CHUNK]
        stmt = insert(Price).values(chunk)
        stmt = stmt.on_conflict_do_update(
            index_elements=[Price.ticker, Price.date],
            set_={
                "open": stmt.excluded.open,
                "high": stmt.excluded.high,
                "low": stmt.excluded.low,
                "close": stmt.excluded.close,
                "volume": stmt.excluded.volume,
            },
        )
        session.execute(stmt)

    return len(rows)
