"""status_sentiment

Adds the derived-enrichment table that holds one FinBERT reading per status.
Purely additive: no existing table or row is touched, so applying this to a
populated archive is safe and `downgrade` loses only derived data (re-derivable
by re-running `archiver score-sentiment`).

Revision ID: 0002_sentiment
Revises: 0001_initial
Create Date: 2026-07-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_sentiment"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "status_sentiment",
        sa.Column("status_id", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("score", sa.Double(), nullable=False),
        sa.Column("positive", sa.Double(), nullable=False),
        sa.Column("negative", sa.Double(), nullable=False),
        sa.Column("neutral", sa.Double(), nullable=False),
        sa.Column("compound", sa.Double(), nullable=False),
        sa.Column("scored_content_hash", sa.String(), nullable=True),
        sa.Column("scored_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["status_id"], ["statuses.id"], name="fk_status_sentiment_status_id_statuses"
        ),
        sa.PrimaryKeyConstraint("status_id", name="pk_status_sentiment"),
    )
    op.create_index("ix_sentiment_label", "status_sentiment", ["label"])
    op.create_index("ix_sentiment_compound", "status_sentiment", ["compound"])


def downgrade() -> None:
    op.drop_index("ix_sentiment_compound", table_name="status_sentiment")
    op.drop_index("ix_sentiment_label", table_name="status_sentiment")
    op.drop_table("status_sentiment")
