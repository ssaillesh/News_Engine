"""End-to-end: parse fixture → normalize → persist via repositories.

Validates that Phase 4 output plugs directly into the Phase 2 storage layer with
real foreign-key enforcement — including the reblog self-FK ordering (the original
must be persisted before the wrapper that points at it).
"""

from __future__ import annotations

from sqlalchemy import func, select

from archiver.parsing import normalize_status, parse_status
from archiver.storage.db import Database
from archiver.storage.models import Media, Status
from archiver.storage.repositories import (
    AccountRepository,
    MediaRepository,
    StatusMetricRepository,
    StatusRepository,
)


async def test_normalize_then_persist_status_with_media(load_fixture, db: Database) -> None:
    raw = load_fixture("status_with_media.json")
    n = normalize_status(parse_status(raw), raw=raw)

    async with db.session() as session, session.begin():
        await AccountRepository(session, db.dialect).upsert(n.account)
        await StatusRepository(session, db.dialect).upsert(n.status)
        await StatusMetricRepository(session, db.dialect).add(n.metric)
        media_repo = MediaRepository(session, db.dialect)
        for media_row in n.media:
            await media_repo.upsert(media_row)

    async with db.session() as session:
        status = await session.get(Status, "222222222222222222")
        assert status is not None
        assert status.content_text == "Look at this link and cc @friend #News #Archive"
        assert status.sensitive is True
        assert await session.scalar(select(func.count()).select_from(Media)) == 1


async def test_persist_reblog_links_original(load_fixture, db: Database) -> None:
    raw = load_fixture("status_reblog.json")
    n = normalize_status(parse_status(raw), raw=raw)
    assert n.reblog_of is not None

    async with db.session() as session, session.begin():
        accounts = AccountRepository(session, db.dialect)
        statuses = StatusRepository(session, db.dialect)
        # reblog_of_id is a soft reference, but we still archive the original.
        await accounts.upsert(n.reblog_of.account)
        await statuses.upsert(n.reblog_of.status)
        await accounts.upsert(n.account)
        await statuses.upsert(n.status)

    async with db.session() as session:
        wrapper = await session.get(Status, "333333333333333333")
        assert wrapper is not None
        assert wrapper.is_reblog is True
        assert wrapper.reblog_of_id == "999999999999999999"
        original = await session.get(Status, "999999999999999999")
        assert original is not None
        assert original.content_text == "Original post that was boosted."
