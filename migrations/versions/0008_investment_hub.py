"""investment hub: securities, price_bars, watchlist, holdings

Purely additive. Company news needs no table of its own: it is archived as
statuses with source="market_news" and linked to tickers via stock_mentions.

Revision ID: 0008_investment_hub
Revises: 0007_analysis
Create Date: 2026-11-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_investment_hub"
down_revision: str | None = "0007_analysis"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
_TS = sa.DateTime(timezone=True)
_F = sa.Double()


def upgrade() -> None:
    op.create_table(
        "securities",
        sa.Column("ticker", sa.String(16), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("exchange", sa.String(), nullable=True),
        sa.Column("currency", sa.String(8), nullable=True),
        sa.Column("country", sa.String(8), nullable=True),
        sa.Column("industry", sa.String(), nullable=True),
        sa.Column("logo_url", sa.String(), nullable=True),
        sa.Column("web_url", sa.String(), nullable=True),
        sa.Column("ipo_date", sa.String(10), nullable=True),
        sa.Column("market_cap", _F, nullable=True),
        sa.Column("shares_outstanding", _F, nullable=True),
        sa.Column("price", _F, nullable=True),
        sa.Column("change", _F, nullable=True),
        sa.Column("pct_change", _F, nullable=True),
        sa.Column("day_open", _F, nullable=True),
        sa.Column("day_high", _F, nullable=True),
        sa.Column("day_low", _F, nullable=True),
        sa.Column("prev_close", _F, nullable=True),
        sa.Column("quote_at", _TS, nullable=True),
        sa.Column("metrics", _JSON, nullable=True),
        sa.Column("recommendation", _JSON, nullable=True),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column("profile_refreshed_at", _TS, nullable=True),
        sa.Column("refreshed_at", _TS, nullable=False),
        sa.PrimaryKeyConstraint("ticker", name="pk_securities"),
    )
    op.create_table(
        "price_bars",
        sa.Column("ticker", sa.String(16), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("open", _F, nullable=True),
        sa.Column("high", _F, nullable=True),
        sa.Column("low", _F, nullable=True),
        sa.Column("close", _F, nullable=True),
        sa.Column("adj_close", _F, nullable=True),
        sa.Column("volume", sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint("ticker", "date", name="pk_price_bars"),
    )
    op.create_table(
        "watchlist",
        sa.Column("ticker", sa.String(16), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("added_at", _TS, nullable=False),
        sa.PrimaryKeyConstraint("ticker", name="pk_watchlist"),
    )
    op.create_table(
        "holdings",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("ticker", sa.String(16), nullable=False),
        sa.Column("shares", _F, nullable=False),
        sa.Column("avg_cost", _F, nullable=False),
        sa.Column("opened_at", sa.Date(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", _TS, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_holdings"),
    )
    op.create_index("ix_holdings_ticker", "holdings", ["ticker"])


def downgrade() -> None:
    op.drop_index("ix_holdings_ticker", table_name="holdings")
    op.drop_table("holdings")
    op.drop_table("watchlist")
    op.drop_table("price_bars")
    op.drop_table("securities")
