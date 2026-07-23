"""stock_mentions + company_market

Adds the two tables behind the stock-tracking feature: derived company mentions
(the Trump watchlist) and a cache of live quote + next-earnings data. Purely
additive; `downgrade` drops only these tables and their (re-derivable) contents.

Revision ID: 0004_stocks
Revises: 0003_summary
Create Date: 2026-07-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_stocks"
down_revision: str | None = "0003_summary"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "stock_mentions",
        sa.Column("status_id", sa.String(), nullable=False),
        sa.Column("ticker", sa.String(), nullable=False),
        sa.Column("alias", sa.String(), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["status_id"], ["statuses.id"], name="fk_stock_mentions_status_id_statuses"
        ),
        sa.PrimaryKeyConstraint("status_id", "ticker", name="pk_stock_mentions"),
    )
    op.create_index("ix_stock_mentions_ticker", "stock_mentions", ["ticker"])

    op.create_table(
        "company_market",
        sa.Column("ticker", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("last_price", sa.String(), nullable=True),
        sa.Column("net_change", sa.String(), nullable=True),
        sa.Column("pct_change", sa.String(), nullable=True),
        sa.Column("delta_indicator", sa.String(), nullable=True),
        sa.Column("market_cap", sa.String(), nullable=True),
        sa.Column("price_as_of", sa.String(), nullable=True),
        sa.Column("next_earnings_date", sa.String(), nullable=True),
        sa.Column("next_earnings_eps_forecast", sa.String(), nullable=True),
        sa.Column("next_earnings_time", sa.String(), nullable=True),
        sa.Column("quote_error", sa.String(), nullable=True),
        sa.Column("refreshed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("ticker", name="pk_company_market"),
    )
    op.create_index("ix_company_market_earnings", "company_market", ["next_earnings_date"])


def downgrade() -> None:
    op.drop_index("ix_company_market_earnings", table_name="company_market")
    op.drop_table("company_market")
    op.drop_index("ix_stock_mentions_ticker", table_name="stock_mentions")
    op.drop_table("stock_mentions")
