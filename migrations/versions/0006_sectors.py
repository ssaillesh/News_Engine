"""status_sectors + stance columns on status_impact

Adds market-sector detection and stance (restrictive / supportive / mentioned).
Sectors answer "what does this affect" for the ~99% of items that name no
company; stance answers "in which direction". Purely additive.

Revision ID: 0006_sectors
Revises: 0005_classification
Create Date: 2026-09-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_sectors"
down_revision: str | None = "0005_classification"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "status_sectors",
        sa.Column("status_id", sa.String(), nullable=False),
        sa.Column("sector", sa.String(), nullable=False),
        sa.Column("matched_term", sa.String(), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["status_id"], ["statuses.id"], name="fk_status_sectors_status_id_statuses"
        ),
        sa.PrimaryKeyConstraint("status_id", "sector", name="pk_status_sectors"),
    )
    op.create_index("ix_status_sectors_sector", "status_sectors", ["sector"])
    op.add_column("status_impact", sa.Column("stance", sa.String(), nullable=True))
    op.add_column(
        "status_impact", sa.Column("stance_confidence", sa.Double(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("status_impact", "stance_confidence")
    op.drop_column("status_impact", "stance")
    op.drop_index("ix_status_sectors_sector", table_name="status_sectors")
    op.drop_table("status_sectors")
