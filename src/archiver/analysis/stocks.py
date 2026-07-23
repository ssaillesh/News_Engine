"""Stock-mention detection: scan archived statuses for watchlist companies.

Pure and dependency-free (no ML, no network) — it runs the curated matcher from
``archiver.reference.tickers`` over ``content_text`` and records one row per
(status, company). The distinct tickers it finds are the Trump watchlist that the
market refresh and the Upcoming Reports tab are built on.

Sources default to Trump's own words plus coverage about him — not the Federal
Register, whose tariff legalese names companies in a very different sense than
"Trump talked about this stock".
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sqlalchemy import select

from archiver.reference.tickers import find_tickers
from archiver.storage.models import Status
from archiver.storage.repositories import StockMentionRepository

if TYPE_CHECKING:
    from archiver.storage.db import Database

# "Mentioned by Trump" = his remarks/messages, White House releases, and news
# coverage about him. Federal Register documents are excluded by default.
DEFAULT_MENTION_SOURCES = ("presidential_documents", "whitehouse", "news")


@dataclass
class MentionReport:
    """What a detection run did."""

    scanned: int = 0
    mentions: int = 0
    ticker_counts: dict[str, int] = field(default_factory=dict)

    def record(self, ticker: str) -> None:
        self.mentions += 1
        self.ticker_counts[ticker] = self.ticker_counts.get(ticker, 0) + 1


async def detect_mentions(
    db: Database,
    *,
    sources: Sequence[str] = DEFAULT_MENTION_SOURCES,
    limit: int | None = None,
) -> MentionReport:
    """Detect company mentions across the selected sources and persist them.

    Idempotent: each status's mentions are cleared and rewritten, so a status
    whose text changed (a company added or removed) ends up correct rather than
    accumulating stale rows. Cheap enough to just re-run over everything.
    """
    report = MentionReport()

    stmt = select(Status).order_by(Status.created_at.desc())
    if sources:
        stmt = stmt.where(Status.source.in_(list(sources)))
    if limit is not None:
        stmt = stmt.limit(limit)

    async with db.session() as session:
        statuses = list((await session.scalars(stmt)).all())

    for status in statuses:
        report.scanned += 1
        hits = find_tickers(status.content_text or "")
        async with db.session() as session, session.begin():
            repo = StockMentionRepository(session, db.dialect)
            await repo.clear_for_status(status.id)
            for ticker, alias in hits.items():
                await repo.upsert(
                    {"status_id": status.id, "ticker": ticker, "alias": alias}
                )
                report.record(ticker)
    return report
