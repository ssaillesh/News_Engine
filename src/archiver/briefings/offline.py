"""The scheduled pass: write briefings for the newest stories that have real text."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import httpx
from loguru import logger
from sqlalchemy import select

from archiver.briefings.articles import fetch_article_text, is_google_news_link
from archiver.briefings.generator import BriefingFailed, BriefingUnavailable
from archiver.storage.models import Status, StatusAnalysis, StatusImpact, utcnow

if TYPE_CHECKING:
    from archiver.briefings.local import LocalBriefingGenerator
    from archiver.storage.db import Database

# Stored text at least this long is a real body (Federal Register full text,
# White House releases); shorter is a headline plus a feed blurb.
_STORED_TEXT_MIN_CHARS = 1500


@dataclass
class WriteReport:
    written: int = 0
    failed: int = 0
    skipped_no_text: int = 0
    skipped_google_news: int = 0
    stopped_for_time: bool = False
    unavailable: str | None = None  # set when the model server could not be reached
    seconds: float = 0.0
    titles: list[str] = field(default_factory=list)


async def write_analyses(
    db: Database,
    generator: LocalBriefingGenerator,
    *,
    limit: int,
    max_minutes: float,
    days: int,
    user_agent: str,
    respect_robots: bool = True,
    http_client: httpx.AsyncClient | None = None,
) -> WriteReport:
    """Write up to ``limit`` briefings, newest high-impact stories first.

    Stops starting new stories once ``max_minutes`` has passed, so the scheduled
    job finishes inside its timeout; a story in progress is always completed.
    """
    report = WriteReport()
    started = time.monotonic()
    since = datetime.now(UTC) - timedelta(days=days)

    stmt = (
        select(Status)
        .outerjoin(StatusAnalysis, StatusAnalysis.status_id == Status.id)
        .outerjoin(StatusImpact, StatusImpact.status_id == Status.id)
        .where(StatusAnalysis.status_id.is_(None))
        .where(Status.created_at >= since.replace(tzinfo=None))
        .order_by(StatusImpact.impact_score.desc().nulls_last(), Status.created_at.desc())
        .limit(limit * 10)  # many candidates are skipped for lack of text
    )
    async with db.session() as session:
        candidates = list((await session.scalars(stmt)).all())

    owns_client = http_client is None
    client = http_client or httpx.AsyncClient(
        timeout=20.0, follow_redirects=True, headers={"User-Agent": user_agent}
    )
    try:
        for status in candidates:
            if report.written >= limit:
                break
            if (time.monotonic() - started) / 60 >= max_minutes:
                report.stopped_for_time = True
                break

            text = (status.content_text or "").strip()
            if len(text) < _STORED_TEXT_MIN_CHARS:
                if is_google_news_link(status.url):
                    report.skipped_google_news += 1
                    continue
                body = await fetch_article_text(
                    status.url, client=client, user_agent=user_agent, respect_robots=respect_robots
                )
                if not body:
                    report.skipped_no_text += 1
                    continue
                title = (status.raw or {}).get("title") or text.split("\n", 1)[0]
                text = f"{title}\n\n{body}"

            try:
                result = await generator.generate(status, text)
            except BriefingUnavailable as exc:
                report.unavailable = str(exc)
                break
            except BriefingFailed as exc:
                report.failed += 1
                logger.warning("analysis failed for {}: {}", status.id, exc)
                continue

            async with db.session() as session, session.begin():
                if await session.get(StatusAnalysis, status.id) is None:
                    session.add(
                        StatusAnalysis(
                            status_id=status.id,
                            model=result.model,
                            source_quality=result.briefing.source_quality,
                            analysis=result.briefing.model_dump(),
                            input_tokens=result.input_tokens,
                            output_tokens=result.output_tokens,
                            generated_at=utcnow(),
                        )
                    )
            report.written += 1
            report.titles.append(text.split("\n", 1)[0][:90])
            logger.info("wrote analysis {} ({} out tokens)", status.id, result.output_tokens)
    finally:
        if owns_client:
            await client.aclose()
    report.seconds = time.monotonic() - started
    return report
