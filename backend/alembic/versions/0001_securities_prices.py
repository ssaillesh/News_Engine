"""securities + prices (prices as a TimescaleDB hypertable)

Revision ID: 0001_securities_prices
Revises:
Create Date: 2026-08-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_securities_prices"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "securities",
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=True),
        sa.Column("exchange", sa.String(length=32), nullable=True),
        sa.Column("sector", sa.String(length=64), nullable=True),
        sa.Column("market_cap", sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint("ticker", name=op.f("pk_securities")),
    )

    op.create_table(
        "prices",
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("open", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("high", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("low", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("close", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("volume", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(
            ["ticker"],
            ["securities.ticker"],
            name=op.f("fk_prices_ticker_securities"),
            ondelete="CASCADE",
        ),
        # (ticker, date) — Timescale requires the partitioning column in every
        # unique constraint, so date must be part of the primary key.
        sa.PrimaryKeyConstraint("ticker", "date", name=op.f("pk_prices")),
    )

    # Hypertable. Both guards are needed: CREATE EXTENSION itself errors on a
    # Postgres that does not ship timescaledb, so availability is checked first.
    # A plain-Postgres environment then gets a working unpartitioned table and a
    # NOTICE, rather than a failed migration.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'timescaledb') THEN
                EXECUTE 'CREATE EXTENSION IF NOT EXISTS timescaledb';
                PERFORM create_hypertable(
                    'prices', 'date',
                    chunk_time_interval => INTERVAL '1 year',
                    migrate_data => TRUE
                );
            ELSE
                RAISE NOTICE 'timescaledb unavailable - prices created as a plain table';
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.drop_table("prices")
    op.drop_table("securities")
