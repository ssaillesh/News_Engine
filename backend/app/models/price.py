"""``prices`` — daily OHLCV bars. A TimescaleDB hypertable on ``date``."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import BigInteger, Date, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Price(Base):
    __tablename__ = "prices"

    # Composite PK (ticker, date) — Timescale requires the partitioning column
    # to be part of every unique constraint on a hypertable.
    ticker: Mapped[str] = mapped_column(
        String(16), ForeignKey("securities.ticker", ondelete="CASCADE"), primary_key=True
    )
    date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    open: Mapped[float | None] = mapped_column(Numeric(18, 4))
    high: Mapped[float | None] = mapped_column(Numeric(18, 4))
    low: Mapped[float | None] = mapped_column(Numeric(18, 4))
    close: Mapped[float | None] = mapped_column(Numeric(18, 4))
    volume: Mapped[int | None] = mapped_column(BigInteger)
