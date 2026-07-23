"""Integration tests for the storage layer (DESIGN.md §5.8, §5.9, §5.10, §6).

Runs against a shared in-memory SQLite database with foreign keys enforced, so
these prove the real guarantees without needing Docker/Postgres:
idempotent upserts, FK integrity, immutable version history, deletion-as-flag,
raw-payload dedup, blob dedup, and in-place checkpoint updates.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from archiver.storage.db import Database
from archiver.storage.models import (
    CheckpointState,
    MediaBlob,
    RawPayload,
    Status,
    StatusMetric,
    StatusVersion,
)
from archiver.storage.repositories import (
    AccountRepository,
    CheckpointRepository,
    MediaBlobRepository,
    RawPayloadRepository,
    StatusMetricRepository,
    StatusRepository,
    StatusVersionRepository,
)


def _account(**over: object) -> dict[str, object]:
    return {"id": "acc1", "username": "realDonaldTrump", **over}


def _status(**over: object) -> dict[str, object]:
    return {
        "id": "s1",
        "account_id": "acc1",
        "created_at": datetime(2020, 1, 1, tzinfo=UTC),
        "content_hash": "hash-v1",
        **over,
    }


async def _count(session, model) -> int:
    return await session.scalar(select(func.count()).select_from(model))


async def _seed_account(db: Database) -> None:
    async with db.session() as session, session.begin():
        await AccountRepository(session, db.dialect).upsert(_account())


# ─────────────────────────────────────────────────────────────────────────────
async def test_status_upsert_is_idempotent(db: Database) -> None:
    await _seed_account(db)
    async with db.session() as session, session.begin():
        repo = StatusRepository(session, db.dialect)
        await repo.upsert(_status())
        await repo.upsert(_status())  # replay — must not duplicate

    async with db.session() as session:
        assert await _count(session, Status) == 1


async def test_status_upsert_updates_mutable_fields(db: Database) -> None:
    await _seed_account(db)
    async with db.session() as session, session.begin():
        await StatusRepository(session, db.dialect).upsert(_status(content_text="hello"))
    async with db.session() as session, session.begin():
        await StatusRepository(session, db.dialect).upsert(
            _status(content_text="hello (edited)", content_hash="hash-v2")
        )
    async with db.session() as session:
        row = await session.get(Status, "s1")
        assert row is not None
        assert row.content_text == "hello (edited)"
        assert row.content_hash == "hash-v2"
        assert await _count(session, Status) == 1


async def test_fk_integrity_rejects_orphan_status(db: Database) -> None:
    # No account seeded → the status.account_id FK must fail.
    with pytest.raises(IntegrityError):
        async with db.session() as session, session.begin():
            await StatusRepository(session, db.dialect).upsert(
                _status(account_id="does-not-exist")
            )


async def test_version_history_is_append_only(db: Database) -> None:
    await _seed_account(db)
    async with db.session() as session, session.begin():
        await StatusRepository(session, db.dialect).upsert(_status())
        versions = StatusVersionRepository(session, db.dialect)
        await versions.append(
            {"status_id": "s1", "version": 1, "content_hash": "hash-v1", "content_text": "orig"}
        )
        await versions.append(
            {"status_id": "s1", "version": 2, "content_hash": "hash-v2", "content_text": "edited"}
        )
        # Replaying version 1 with different content must NOT overwrite history.
        await versions.append(
            {"status_id": "s1", "version": 1, "content_hash": "hash-v1", "content_text": "TAMPERED"}
        )

    async with db.session() as session:
        assert await _count(session, StatusVersion) == 2
        assert await StatusVersionRepository(session, db.dialect).latest_version("s1") == 2
        v1 = await session.scalar(
            select(StatusVersion).where(
                StatusVersion.status_id == "s1", StatusVersion.version == 1
            )
        )
        assert v1 is not None
        assert v1.content_text == "orig"  # untampered


async def test_mark_deleted_retains_the_row(db: Database) -> None:
    await _seed_account(db)
    async with db.session() as session, session.begin():
        await StatusRepository(session, db.dialect).upsert(_status(content_text="important post"))

    async with db.session() as session, session.begin():
        found = await StatusRepository(session, db.dialect).mark_deleted("s1")
        assert found is True

    async with db.session() as session:
        row = await session.get(Status, "s1")
        assert row is not None  # NOT removed
        assert row.is_deleted is True
        assert row.deleted_detected_at is not None
        assert row.content_text == "important post"  # content preserved


async def test_raw_payload_dedup_by_hash(db: Database) -> None:
    async with db.session() as session, session.begin():
        repo = RawPayloadRepository(session, db.dialect)
        await repo.save({"endpoint": "/statuses", "payload": {"a": 1}, "payload_sha256": "abc"})
        await repo.save({"endpoint": "/statuses", "payload": {"a": 1}, "payload_sha256": "abc"})
    async with db.session() as session:
        assert await _count(session, RawPayload) == 1


async def test_media_blob_dedup_by_checksum(db: Database) -> None:
    async with db.session() as session, session.begin():
        repo = MediaBlobRepository(session, db.dialect)
        await repo.upsert({"sha256": "deadbeef", "byte_size": 100, "mime_type": "image/jpeg"})
        await repo.upsert({"sha256": "deadbeef", "byte_size": 100, "mime_type": "image/jpeg"})
    async with db.session() as session:
        assert await _count(session, MediaBlob) == 1


async def test_checkpoint_updates_in_place(db: Database) -> None:
    await _seed_account(db)
    async with db.session() as session, session.begin():
        repo = CheckpointRepository(session, db.dialect)
        await repo.upsert(
            {"target_account_id": "acc1", "phase": "backfill", "frontier_cursor": "10"}
        )
    async with db.session() as session, session.begin():
        repo = CheckpointRepository(session, db.dialect)
        await repo.upsert(
            {"target_account_id": "acc1", "phase": "monitor", "frontier_cursor": "42"}
        )

    async with db.session() as session:
        assert await _count(session, CheckpointState) == 1
        cp = await session.get(CheckpointState, "acc1")
        assert cp is not None
        assert cp.phase == "monitor"
        assert cp.frontier_cursor == "42"


async def test_metrics_are_time_series(db: Database) -> None:
    await _seed_account(db)
    async with db.session() as session, session.begin():
        await StatusRepository(session, db.dialect).upsert(_status())
        metrics = StatusMetricRepository(session, db.dialect)
        await metrics.add({"status_id": "s1", "replies_count": 1, "reblogs_count": 2})
        await metrics.add({"status_id": "s1", "replies_count": 5, "reblogs_count": 9})
    async with db.session() as session:
        assert await _count(session, StatusMetric) == 2  # both retained
