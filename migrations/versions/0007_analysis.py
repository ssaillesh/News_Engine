"""status_analysis

Stores the on-demand, AI-written breakdown of a story so each one is generated
at most once. Purely additive; contents are re-derivable by generating again.

Revision ID: 0007_analysis
Revises: 0006_sectors
Create Date: 2026-09-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_analysis"
down_revision: str | None = "0006_sectors"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "status_analysis",
        sa.Column("status_id", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("source_quality", sa.String(), nullable=False),
        sa.Column(
            "analysis",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["status_id"], ["statuses.id"], name="fk_status_analysis_status_id_statuses"
        ),
        sa.PrimaryKeyConstraint("status_id", name="pk_status_analysis"),
    )
    op.create_index("ix_status_analysis_generated", "status_analysis", ["generated_at"])


def downgrade() -> None:
    op.drop_index("ix_status_analysis_generated", table_name="status_analysis")
    op.drop_table("status_analysis")
