"""status_topics + status_entities + status_impact

Adds the three derived tables behind impact ranking: curated topic hits, named
countries/blocs/agencies, and the score with its components. Purely additive;
`downgrade` drops only these tables, whose contents are all re-derivable by
re-running `archiver classify`.

Revision ID: 0005_classification
Revises: 0004_stocks
Create Date: 2026-09-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_classification"
down_revision: str | None = "0004_stocks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "status_topics",
        sa.Column("status_id", sa.String(), nullable=False),
        sa.Column("topic", sa.String(), nullable=False),
        sa.Column("matched_term", sa.String(), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["status_id"], ["statuses.id"], name="fk_status_topics_status_id_statuses"
        ),
        sa.PrimaryKeyConstraint("status_id", "topic", name="pk_status_topics"),
    )
    op.create_index("ix_status_topics_topic", "status_topics", ["topic"])

    op.create_table(
        "status_entities",
        sa.Column("status_id", sa.String(), nullable=False),
        sa.Column("entity_key", sa.String(), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("alias", sa.String(), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["status_id"], ["statuses.id"], name="fk_status_entities_status_id_statuses"
        ),
        sa.PrimaryKeyConstraint("status_id", "entity_key", name="pk_status_entities"),
    )
    op.create_index("ix_status_entities_key", "status_entities", ["entity_key"])
    op.create_index("ix_status_entities_type", "status_entities", ["entity_type"])

    op.create_table(
        "status_impact",
        sa.Column("status_id", sa.String(), nullable=False),
        sa.Column("authority", sa.Double(), nullable=False),
        sa.Column("authority_label", sa.String(), nullable=True),
        sa.Column("topic", sa.Double(), nullable=False),
        sa.Column("actionability", sa.Double(), nullable=False),
        # Nullable on purpose: NULL means "not measured yet" and is excluded from
        # the weighted average; 0.0 would mean "measured, no support".
        sa.Column("corroboration", sa.Double(), nullable=True),
        sa.Column("market_sensitivity", sa.Double(), nullable=True),
        sa.Column("impact_score", sa.Double(), nullable=False),
        sa.Column("tier", sa.String(), nullable=False),
        sa.Column("weights_version", sa.String(), nullable=False),
        sa.Column("scored_content_hash", sa.String(), nullable=True),
        sa.Column("scored_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["status_id"], ["statuses.id"], name="fk_status_impact_status_id_statuses"
        ),
        sa.PrimaryKeyConstraint("status_id", name="pk_status_impact"),
    )
    op.create_index("ix_status_impact_score", "status_impact", ["impact_score"])
    op.create_index("ix_status_impact_tier", "status_impact", ["tier"])


def downgrade() -> None:
    op.drop_index("ix_status_impact_tier", table_name="status_impact")
    op.drop_index("ix_status_impact_score", table_name="status_impact")
    op.drop_table("status_impact")
    op.drop_index("ix_status_entities_type", table_name="status_entities")
    op.drop_index("ix_status_entities_key", table_name="status_entities")
    op.drop_table("status_entities")
    op.drop_index("ix_status_topics_topic", table_name="status_topics")
    op.drop_table("status_topics")
