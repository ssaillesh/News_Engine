"""universe: security_type, sector, tags, is_core on securities

Revision ID: 0009_universe
Revises: 0008_investment_hub
Create Date: 2026-11-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_universe"
down_revision: str | None = "0008_investment_hub"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    with op.batch_alter_table("securities") as batch:
        batch.add_column(sa.Column("security_type", sa.String(32), nullable=True))
        batch.add_column(sa.Column("sector", sa.String(64), nullable=True))
        batch.add_column(sa.Column("tags", _JSON, nullable=True))
        batch.add_column(
            sa.Column("is_core", sa.Boolean(), nullable=False, server_default=sa.false())
        )
    op.create_index("ix_securities_is_core", "securities", ["is_core"])


def downgrade() -> None:
    op.drop_index("ix_securities_is_core", table_name="securities")
    with op.batch_alter_table("securities") as batch:
        batch.drop_column("is_core")
        batch.drop_column("tags")
        batch.drop_column("sector")
        batch.drop_column("security_type")
