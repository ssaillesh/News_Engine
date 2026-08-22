"""``securities`` — one row per publicly traded company we track."""

from __future__ import annotations

from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Security(Base):
    __tablename__ = "securities"

    ticker: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(256))
    exchange: Mapped[str | None] = mapped_column(String(32))
    sector: Mapped[str | None] = mapped_column(String(64))
    market_cap: Mapped[int | None] = mapped_column(BigInteger)
