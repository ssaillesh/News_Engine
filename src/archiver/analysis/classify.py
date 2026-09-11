"""The deterministic classification pass: topics, entities, and impact scores.

Offline and dependency-free — no network, no ML, no torch. It runs the curated
matchers from :mod:`archiver.reference.topics` and
:mod:`archiver.reference.entities` plus the pure scorers in
:mod:`archiver.analysis.signals`, and writes derived rows alongside the captured
record. Being regex-and-lookups only, it belongs in the fast ingest workflow
rather than the heavy enrichment one, and a full pass over the archive costs
seconds.

All sources are classified by default, unlike stock detection: a tariff
proclamation in the Federal Register is exactly the high-authority item this
ranking exists to surface, so excluding it would defeat the purpose.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from archiver.analysis.signals import (
    WEIGHTS_VERSION,
    actionability_score,
    authority_score,
    combine,
    market_sensitivity_score,
    tier_for,
)
from archiver.reference.entities import find_entities
from archiver.reference.topics import find_topics, topic_weight
from archiver.storage.models import Status, StatusImpact, StockMention
from archiver.storage.repositories import (
    StatusEntityRepository,
    StatusImpactRepository,
    StatusTopicRepository,
)

if TYPE_CHECKING:
    from archiver.storage.db import Database


@dataclass
class ClassifyReport:
    """What a classification run did."""

    scanned: int = 0
    skipped_empty: int = 0
    topic_counts: dict[str, int] = field(default_factory=dict)
    entity_counts: dict[str, int] = field(default_factory=dict)
    tier_counts: dict[str, int] = field(default_factory=dict)
    market_flagged: int = 0

    def record_topic(self, topic: str) -> None:
        self.topic_counts[topic] = self.topic_counts.get(topic, 0) + 1

    def record_entity(self, key: str) -> None:
        self.entity_counts[key] = self.entity_counts.get(key, 0) + 1

    def record_tier(self, tier: str) -> None:
        self.tier_counts[tier] = self.tier_counts.get(tier, 0) + 1


def _classifiable_text(status: Status) -> str:
    """The full text to match against.

    Unlike sentiment scoring, this wants the whole body rather than the first
    line: a country or a tariff term can appear anywhere in it. Falls back to
    the raw payload's title, which is all the official sources currently store.
    """
    text = (status.content_text or "").strip()
    if text:
        return text
    raw = status.raw or {}
    return str(raw.get("title") or "").strip()


async def classify_statuses(
    db: Database,
    *,
    sources: Sequence[str] = (),
    limit: int | None = None,
    reclassify: bool = False,
) -> ClassifyReport:
    """Classify archived statuses and persist topics, entities, and impact.

    Idempotent: topic and entity rows are cleared and rewritten per status, so a
    term removed from the lexicon stops appearing rather than lingering. By
    default only unclassified, edited, or differently-weighted rows are visited,
    making a scheduled run after each ingest cost exactly the new items;
    ``reclassify=True`` forces a full redo, which is the right move after
    editing a lexicon or the weights.
    """
    report = ClassifyReport()

    stmt = (
        select(Status)
        .options(selectinload(Status.sentiment))
        .order_by(Status.created_at.desc())
    )
    if sources:
        stmt = stmt.where(Status.source.in_(list(sources)))
    if not reclassify:
        # One query covers "never classified", "text changed since", and
        # "scored under an older weight set".
        stmt = stmt.outerjoin(StatusImpact).where(
            or_(
                StatusImpact.status_id.is_(None),
                StatusImpact.weights_version != WEIGHTS_VERSION,
                StatusImpact.scored_content_hash.is_distinct_from(Status.content_hash),
            )
        )
    if limit is not None:
        stmt = stmt.limit(limit)

    async with db.session() as session:
        pending = list((await session.scalars(stmt)).all())

    # Components owned by later passes must survive a re-run of this one, and
    # they also belong in the weighted average, so read them back first.
    existing: dict[str, tuple[float | None, float | None]] = {}
    if pending:
        ids = [s.id for s in pending]
        async with db.session() as session:
            rows = await session.execute(
                select(
                    StatusImpact.status_id,
                    StatusImpact.corroboration,
                    StatusImpact.market_sensitivity,
                ).where(StatusImpact.status_id.in_(ids))
            )
            existing = {r[0]: (r[1], r[2]) for r in rows}

    # Market sensitivity needs the stock pass's output. Whether that pass has
    # ever run is the difference between "no company named" (0.0, a real
    # measurement) and "nobody has looked" (None, excluded from the average), so
    # check the table once rather than guessing per row.
    mentions: dict[str, int] = {}
    stocks_detected = False
    if pending:
        ids = [s.id for s in pending]
        async with db.session() as session:
            stocks_detected = bool(
                await session.scalar(select(StockMention.status_id).limit(1))
            )
            rows = await session.execute(
                select(StockMention.status_id, func.count())
                .where(StockMention.status_id.in_(ids))
                .group_by(StockMention.status_id)
            )
            mentions = {r[0]: r[1] for r in rows}

    for status in pending:
        report.scanned += 1
        text = _classifiable_text(status)
        if not text:
            report.skipped_empty += 1
            continue

        topics = find_topics(text)
        entities = find_entities(text)
        authority, authority_label = authority_score(status.source, status.raw)
        actionability = actionability_score(text)
        topic_score = topic_weight(list(topics))

        corroboration, _prior_market = existing.get(status.id, (None, None))
        market_sensitivity = (
            market_sensitivity_score(
                mentions.get(status.id, 0),
                status.sentiment.compound if status.sentiment else None,
            )
            if stocks_detected
            else _prior_market
        )
        if market_sensitivity is not None and market_sensitivity > 0:
            report.market_flagged += 1
        score = combine(
            {
                "authority": authority,
                "topic": topic_score,
                "actionability": actionability,
                "corroboration": corroboration,
                "market_sensitivity": market_sensitivity,
            }
        )
        tier = tier_for(score)

        async with db.session() as session, session.begin():
            topic_repo = StatusTopicRepository(session, db.dialect)
            entity_repo = StatusEntityRepository(session, db.dialect)
            impact_repo = StatusImpactRepository(session, db.dialect)

            await topic_repo.clear_for_status(status.id)
            for key, term in topics.items():
                await topic_repo.upsert(
                    {"status_id": status.id, "topic": key, "matched_term": term}
                )
                report.record_topic(key)

            await entity_repo.clear_for_status(status.id)
            for key, (kind, alias) in entities.items():
                await entity_repo.upsert(
                    {
                        "status_id": status.id,
                        "entity_key": key,
                        "entity_type": kind,
                        "alias": alias,
                    }
                )
                report.record_entity(key)

            await impact_repo.upsert(
                {
                    "status_id": status.id,
                    "authority": authority,
                    "authority_label": authority_label,
                    "topic": topic_score,
                    "actionability": actionability,
                    "corroboration": corroboration,
                    "market_sensitivity": market_sensitivity,
                    "impact_score": score,
                    "tier": tier,
                    "weights_version": WEIGHTS_VERSION,
                    "scored_content_hash": status.content_hash,
                }
            )
        report.record_tier(tier)

    return report
