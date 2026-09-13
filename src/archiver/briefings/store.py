"""Generate-once storage for briefings."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from archiver.briefings.generator import BriefingFailed, BriefingGenerator
from archiver.storage.models import Status, StatusAnalysis, utcnow

if TYPE_CHECKING:
    from archiver.storage.db import Database

# Two readers opening the same story at once should cause one generation, not
# two. This covers a single process; separate serverless instances can still
# race, and the insert below tolerates that by keeping the first row written.
_locks: dict[str, asyncio.Lock] = {}


async def get_briefing(db: Database, status_id: str) -> StatusAnalysis | None:
    async with db.session() as session:
        return await session.get(StatusAnalysis, status_id)


async def get_or_create_briefing(
    db: Database,
    status_id: str,
    generator: BriefingGenerator,
    *,
    daily_limit: int,
) -> StatusAnalysis:
    """Return the stored briefing, generating it first if there is none.

    Raises ``LookupError`` for an unknown story and ``BriefingFailed`` when the
    daily generation cap is reached, so spend stays bounded however the page is
    used.
    """
    lock = _locks.setdefault(status_id, asyncio.Lock())
    async with lock:
        async with db.session() as session:
            existing = await session.get(StatusAnalysis, status_id)
            if existing is not None:
                return existing
            status = await session.get(Status, status_id)
            if status is None:
                raise LookupError(status_id)
            midnight = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
            today = await session.scalar(
                select(func.count())
                .select_from(StatusAnalysis)
                .where(StatusAnalysis.generated_at >= midnight)
            )
        if (today or 0) >= daily_limit:
            raise BriefingFailed(
                f"Today's limit of {daily_limit} new analyses has been reached. "
                "Stored analyses still load.",
                retryable=False,
                limit_reached=True,
            )

        result = await generator.generate(status)
        row = StatusAnalysis(
            status_id=status_id,
            model=result.model,
            source_quality=result.briefing.source_quality,
            analysis=result.briefing.model_dump(),
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            generated_at=utcnow(),
        )
        async with db.session() as session, session.begin():
            if await session.get(StatusAnalysis, status_id) is None:
                session.add(row)
        stored = await get_briefing(db, status_id)
        return stored if stored is not None else row
