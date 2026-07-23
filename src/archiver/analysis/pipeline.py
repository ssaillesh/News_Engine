"""The sentiment enrichment pass: read archived statuses, write derived readings.

Resumable and cheap to re-run. By default it scores only what has no reading yet
or whose text has changed since it was last scored, so a scheduled run after each
ingest costs exactly the new items. ``rescore=True`` forces a full redo — the
right move after changing the model.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sqlalchemy import or_, select

from archiver.analysis.sentiment import (
    DEFAULT_BATCH_SIZE,
    FINBERT_MODEL,
    FinBertScorer,
)
from archiver.analysis.summarize import DEFAULT_BATCH_SIZE as SUMMARY_BATCH_SIZE
from archiver.analysis.summarize import (
    MIN_CHARS_TO_SUMMARIZE,
    SUMMARY_MODEL,
    Summarizer,
)
from archiver.storage.models import Status, StatusSentiment, StatusSummary
from archiver.storage.repositories import (
    StatusSentimentRepository,
    StatusSummaryRepository,
)

if TYPE_CHECKING:
    from archiver.storage.db import Database

# Which sources get scored by default. FinBERT reads news prose; proclamation and
# executive-order legalese is out of its training distribution and mostly yields
# low-confidence neutral, so the news feed is the default target.
DEFAULT_SOURCES = ("news",)


@dataclass
class ScoreReport:
    """What a scoring run did."""

    scored: int = 0
    skipped_empty: int = 0
    label_counts: dict[str, int] = field(default_factory=dict)

    def record(self, label: str) -> None:
        self.scored += 1
        self.label_counts[label] = self.label_counts.get(label, 0) + 1


def _scoreable_text(status: Status) -> str:
    """The text to feed the model.

    Headlines carry the sentiment for news items and are what FinBERT handles
    best, so we score the first line and let the tokenizer truncate anything
    longer. Falls back to the raw title when ``content_text`` is empty.
    """
    text = (status.content_text or "").strip()
    if text:
        return text.split("\n", 1)[0].strip() or text
    raw = status.raw or {}
    return str(raw.get("title") or "").strip()


async def score_statuses(
    db: Database,
    *,
    sources: Sequence[str] = DEFAULT_SOURCES,
    model_name: str = FINBERT_MODEL,
    batch_size: int = DEFAULT_BATCH_SIZE,
    limit: int | None = None,
    rescore: bool = False,
    device: str | None = None,
    scorer: FinBertScorer | None = None,
) -> ScoreReport:
    """Score archived statuses with FinBERT and persist the readings.

    ``scorer`` is injectable so tests can exercise the pass without the ML stack.
    """
    report = ScoreReport()
    engine = scorer or FinBertScorer(model_name, device=device)
    # Always compare against the model that will actually do the scoring, so an
    # injected scorer and the staleness query can never disagree about what
    # "already scored with this model" means.
    effective_model = engine.model_name

    stmt = select(Status).order_by(Status.created_at.desc())
    if sources:
        stmt = stmt.where(Status.source.in_(list(sources)))
    if not rescore:
        # Outer-join so "never scored" and "scored against different text" are one
        # query; a status edited after scoring is stale and gets picked back up.
        stmt = stmt.outerjoin(StatusSentiment).where(
            or_(
                StatusSentiment.status_id.is_(None),
                StatusSentiment.model != effective_model,
                StatusSentiment.scored_content_hash.is_distinct_from(Status.content_hash),
            )
        )
    if limit is not None:
        stmt = stmt.limit(limit)

    async with db.session() as session:
        pending = list((await session.scalars(stmt)).all())

    batch: list[Status] = []
    for status in pending:
        if not _scoreable_text(status):
            report.skipped_empty += 1
            continue
        batch.append(status)
        if len(batch) >= batch_size:
            await _flush(db, engine, batch, report)
            batch = []
    if batch:
        await _flush(db, engine, batch, report)

    return report


async def _flush(
    db: Database,
    scorer: FinBertScorer,
    batch: Sequence[Status],
    report: ScoreReport,
) -> None:
    """Score one batch and commit its readings together."""
    readings = scorer.score([_scoreable_text(s) for s in batch])
    async with db.session() as session, session.begin():
        repo = StatusSentimentRepository(session, db.dialect)
        for status, reading in zip(batch, readings, strict=True):
            await repo.upsert(reading.as_row(status.id, content_hash=status.content_hash))
            report.record(reading.label)


# ─────────────────────────────────────────────────────────────────────────────
# Summarization
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class SummaryReport:
    """What a summarization run did."""

    summarized: int = 0
    skipped_short: int = 0


def _summarizable_text(status: Status) -> str:
    """The text to condense: the article body, without the headline.

    The headline is already displayed above the summary, so feeding it back in
    just invites the model to echo it instead of adding anything.
    """
    text = (status.content_text or "").strip()
    if "\n" in text:
        return text.split("\n", 1)[1].strip()
    return text


async def summarize_statuses(
    db: Database,
    *,
    sources: Sequence[str] = DEFAULT_SOURCES,
    model_name: str = SUMMARY_MODEL,
    batch_size: int = SUMMARY_BATCH_SIZE,
    limit: int | None = None,
    regenerate: bool = False,
    device: str | None = None,
    min_chars: int = MIN_CHARS_TO_SUMMARIZE,
    summarizer: Summarizer | None = None,
) -> SummaryReport:
    """Condense archived article bodies and persist the generated summaries.

    Incremental on the same terms as the sentiment pass: only never-summarized,
    edited, or different-model items are regenerated. ``summarizer`` is
    injectable so tests can run without the ML stack.
    """
    report = SummaryReport()
    engine = summarizer or Summarizer(model_name, device=device)
    effective_model = engine.model_name

    stmt = select(Status).order_by(Status.created_at.desc())
    if sources:
        stmt = stmt.where(Status.source.in_(list(sources)))
    if not regenerate:
        stmt = stmt.outerjoin(StatusSummary).where(
            or_(
                StatusSummary.status_id.is_(None),
                StatusSummary.model != effective_model,
                StatusSummary.source_content_hash.is_distinct_from(Status.content_hash),
            )
        )
    if limit is not None:
        stmt = stmt.limit(limit)

    async with db.session() as session:
        pending = list((await session.scalars(stmt)).all())

    batch: list[Status] = []
    for status in pending:
        if len(_summarizable_text(status)) < min_chars:
            report.skipped_short += 1
            continue
        batch.append(status)
        if len(batch) >= batch_size:
            await _flush_summaries(db, engine, batch, report)
            batch = []
    if batch:
        await _flush_summaries(db, engine, batch, report)

    return report


async def _flush_summaries(
    db: Database,
    summarizer: Summarizer,
    batch: Sequence[Status],
    report: SummaryReport,
) -> None:
    """Summarize one batch and commit the results together."""
    summaries = summarizer.summarize([_summarizable_text(s) for s in batch])
    async with db.session() as session, session.begin():
        repo = StatusSummaryRepository(session, db.dialect)
        for status, summary in zip(batch, summaries, strict=True):
            if not summary.strip():
                continue
            await repo.upsert(
                {
                    "status_id": status.id,
                    "model": summarizer.model_name,
                    "summary": summary.strip(),
                    "source_content_hash": status.content_hash,
                }
            )
            report.summarized += 1
