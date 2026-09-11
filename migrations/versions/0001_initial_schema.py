"""initial schema

Builds the full archive schema from the ORM metadata, which is the single source
of truth (DESIGN.md §6). Using ``metadata.create_all`` here — rather than a
transcribed ``op.create_table`` block — guarantees the migration honors the
per-dialect type variants (JSONB on PostgreSQL, INTEGER surrogate PKs on SQLite)
exactly as the models define them, avoiding autogenerate's lossy variant handling.

Subsequent, incremental migrations should use standard ``op.*`` operations
(autogenerate is wired up in env.py with ``compare_type`` and batch mode).

Because the metadata is read live, it also contains tables introduced by *later*
revisions. Those are excluded below: creating them here would make this revision
mean something different than it did when it was written, and 0002-0004 would
then fail with "already exists" on any fresh database.

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-22
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from alembic import op

from archiver.storage.models import Base

# Tables added by later revisions. Keep in sync when a revision adds a table:
# the entry pins that table to the revision that introduces it.
_ADDED_LATER = frozenset(
    {
        "status_sentiment",  # 0002_sentiment
        "status_summary",  # 0003_summary
        "stock_mentions",  # 0004_stocks
        "company_market",  # 0004_stocks
        "status_topics",  # 0005_classification
        "status_entities",  # 0005_classification
        "status_impact",  # 0005_classification
    }
)

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _tables_at_this_revision() -> list[Any]:
    return [t for name, t in Base.metadata.tables.items() if name not in _ADDED_LATER]


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind(), tables=_tables_at_this_revision())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind(), tables=_tables_at_this_revision())
