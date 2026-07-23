"""Storage layer: ORM models, async engine/session, and repositories.

Phase 2 deliverable — schema + persistence only. No network/collection code.
Mirrors DESIGN.md §6. Portable across SQLite (tests/minimal) and PostgreSQL
(production): JSON columns become JSONB on Postgres, upserts are dialect-aware.
"""

from archiver.storage.db import Database
from archiver.storage.models import Base, metadata

__all__ = ["Base", "Database", "metadata"]
