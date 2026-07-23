"""Repositories — the only place that reads/writes the archive tables.

Design goals (DESIGN.md §1.5, §5.8, §6):
  * **Idempotency:** every write is an upsert keyed on the platform's natural ID,
    so replaying a fetch never creates duplicates ("exactly-once storage").
  * **Append-only history:** versions and metrics are inserted, never overwritten.
  * **Deletion is a state transition:** ``mark_deleted`` flips a flag; it never
    removes archived rows.
  * **Dialect-aware:** ``ON CONFLICT`` works on both PostgreSQL and SQLite.

Repositories take a live ``AsyncSession`` and the dialect name; the caller owns the
transaction boundary (``async with session.begin(): ...``) so related writes commit
atomically — e.g. a status plus its checkpoint (DESIGN.md §5.10).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import FromClause, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from archiver.storage.models import (
    Account,
    CheckpointState,
    Media,
    MediaBlob,
    RawPayload,
    Status,
    StatusMetric,
    StatusVersion,
    utcnow,
)


def _insert_for(dialect: str) -> Any:
    """Return the dialect-specific INSERT constructor supporting ON CONFLICT."""
    if dialect == "postgresql":
        return pg_insert
    if dialect == "sqlite":
        return sqlite_insert
    raise NotImplementedError(f"Upsert not implemented for dialect {dialect!r}")


async def _upsert(
    session: AsyncSession,
    dialect: str,
    table: FromClause,
    values: Mapping[str, Any],
    *,
    index_elements: Sequence[str],
    update_columns: Sequence[str] | None,
) -> None:
    """INSERT ... ON CONFLICT DO UPDATE/NOTHING for the given conflict target."""
    stmt = _insert_for(dialect)(table).values(**values)
    if update_columns:
        stmt = stmt.on_conflict_do_update(
            index_elements=list(index_elements),
            set_={col: getattr(stmt.excluded, col) for col in update_columns},
        )
    else:
        stmt = stmt.on_conflict_do_nothing(index_elements=list(index_elements))
    await session.execute(stmt)


class _Repo:
    def __init__(self, session: AsyncSession, dialect: str) -> None:
        self.session = session
        self.dialect = dialect


# ─────────────────────────────────────────────────────────────────────────────
class AccountRepository(_Repo):
    _UPDATABLE = (
        "username",
        "acct",
        "display_name",
        "url",
        "last_checked_at",
        "is_active_target",
        "raw",
    )

    async def upsert(self, values: Mapping[str, Any]) -> None:
        await _upsert(
            self.session,
            self.dialect,
            Account.__table__,
            values,
            index_elements=["id"],
            update_columns=self._UPDATABLE,
        )

    async def get(self, account_id: str) -> Account | None:
        return await self.session.get(Account, account_id)


# ─────────────────────────────────────────────────────────────────────────────
class StatusRepository(_Repo):
    _UPDATABLE = (
        "edited_at",
        "url",
        "uri",
        "in_reply_to_id",
        "in_reply_to_account_id",
        "reblog_of_id",
        "is_reblog",
        "visibility",
        "sensitive",
        "spoiler_text",
        "language",
        "content_html",
        "content_text",
        "content_hash",
        "kind",
        "current_version",
        "last_seen_at",
        "raw",
    )

    async def upsert(self, values: Mapping[str, Any]) -> None:
        await _upsert(
            self.session,
            self.dialect,
            Status.__table__,
            values,
            index_elements=["id"],
            update_columns=self._UPDATABLE,
        )

    async def get(self, status_id: str) -> Status | None:
        return await self.session.get(Status, status_id)

    async def mark_deleted(self, status_id: str, *, when: datetime | None = None) -> bool:
        """Flag a status deleted without removing it. Returns True if found."""
        status = await self.session.get(Status, status_id)
        if status is None:
            return False
        status.is_deleted = True
        status.deleted_detected_at = when or utcnow()
        return True

    async def touch_last_seen(self, status_id: str, *, when: datetime | None = None) -> None:
        status = await self.session.get(Status, status_id)
        if status is not None:
            status.last_seen_at = when or utcnow()


# ─────────────────────────────────────────────────────────────────────────────
class StatusVersionRepository(_Repo):
    async def append(self, values: Mapping[str, Any]) -> None:
        """Insert an immutable version row (idempotent on (status_id, version))."""
        await _upsert(
            self.session,
            self.dialect,
            StatusVersion.__table__,
            values,
            index_elements=["status_id", "version"],
            update_columns=None,  # never overwrite history
        )

    async def latest_version(self, status_id: str) -> int:
        stmt = (
            select(StatusVersion.version)
            .where(StatusVersion.status_id == status_id)
            .order_by(StatusVersion.version.desc())
            .limit(1)
        )
        result = await self.session.scalar(stmt)
        return result or 0


# ─────────────────────────────────────────────────────────────────────────────
class StatusMetricRepository(_Repo):
    async def add(self, values: Mapping[str, Any]) -> None:
        self.session.add(StatusMetric(**dict(values)))


# ─────────────────────────────────────────────────────────────────────────────
class MediaRepository(_Repo):
    _UPDATABLE = (
        "type",
        "url",
        "preview_url",
        "remote_url",
        "description",
        "blurhash",
        "meta",
        "blob_sha256",
    )

    async def upsert(self, values: Mapping[str, Any]) -> None:
        await _upsert(
            self.session,
            self.dialect,
            Media.__table__,
            values,
            index_elements=["id"],
            update_columns=self._UPDATABLE,
        )


class MediaBlobRepository(_Repo):
    async def upsert(self, values: Mapping[str, Any]) -> None:
        """Content-addressed; identical media dedupes to one blob row."""
        await _upsert(
            self.session,
            self.dialect,
            MediaBlob.__table__,
            values,
            index_elements=["sha256"],
            update_columns=None,
        )


# ─────────────────────────────────────────────────────────────────────────────
class RawPayloadRepository(_Repo):
    async def save(self, values: Mapping[str, Any]) -> None:
        """Append a raw capture, deduped by payload hash (capture-before-process)."""
        await _upsert(
            self.session,
            self.dialect,
            RawPayload.__table__,
            values,
            index_elements=["payload_sha256"],
            update_columns=None,
        )


# ─────────────────────────────────────────────────────────────────────────────
class CheckpointRepository(_Repo):
    _UPDATABLE = (
        "phase",
        "backfill_cursor",
        "frontier_cursor",
        "backfill_complete",
        "last_resync_at",
        "updated_at",
    )

    async def upsert(self, values: Mapping[str, Any]) -> None:
        payload = {**values}
        payload.setdefault("updated_at", utcnow())
        await _upsert(
            self.session,
            self.dialect,
            CheckpointState.__table__,
            payload,
            index_elements=["target_account_id"],
            update_columns=self._UPDATABLE,
        )

    async def get(self, account_id: str) -> CheckpointState | None:
        return await self.session.get(CheckpointState, account_id)
