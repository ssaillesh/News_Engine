"""status_summary

Adds the derived table holding one machine-generated summary per status. Purely
additive, like 0002: no existing table or row is touched, and `downgrade` loses
only derived data (re-derivable by re-running `archiver summarize`).

Revision ID: 0003_summary
Revises: 0002_sentiment
Create Date: 2026-07-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_summary"
down_revision: str | None = "0002_sentiment"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "status_summary",
        sa.Column("status_id", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("source_content_hash", sa.String(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["status_id"], ["statuses.id"], name="fk_status_summary_status_id_statuses"
        ),
        sa.PrimaryKeyConstraint("status_id", name="pk_status_summary"),
    )


def downgrade() -> None:
    op.drop_table("status_summary")
