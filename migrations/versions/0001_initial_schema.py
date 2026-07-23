"""initial schema

Builds the full archive schema from the ORM metadata, which is the single source
of truth (DESIGN.md §6). Using ``metadata.create_all`` here — rather than a
transcribed ``op.create_table`` block — guarantees the migration honors the
per-dialect type variants (JSONB on PostgreSQL, INTEGER surrogate PKs on SQLite)
exactly as the models define them, avoiding autogenerate's lossy variant handling.

Subsequent, incremental migrations should use standard ``op.*`` operations
(autogenerate is wired up in env.py with ``compare_type`` and batch mode).

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-22
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from archiver.storage.models import Base

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
