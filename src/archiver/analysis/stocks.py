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
from archiver.storage.models import Status, StockMention
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
    # Rows actually written / deleted this run (the diff against what was stored).
    added: int = 0
    removed: int = 0

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

    Idempotent: the stored mentions for the scanned statuses end up exactly equal
    to what the matcher finds now, so a status whose text changed (a company
    added or removed) is corrected rather than accumulating stale rows.

    Matching runs in memory and only the *difference* against what is stored is
    written, in one transaction. Rewriting every status in its own transaction
    cost several round trips per row — tens of thousands against a remote
    Postgres — which outran the scheduled job's timeout and stalled every step
    after it.
    """
    report = MentionReport()

    # Only the two columns matching needs: full rows drag `raw`/`content_html`.
    stmt = select(Status.id, Status.content_text).order_by(Status.created_at.desc())
    if sources:
        stmt = stmt.where(Status.source.in_(list(sources)))
    if limit is not None:
        stmt = stmt.limit(limit)

    async with db.session() as session:
        rows = (await session.execute(stmt)).all()

    wanted: dict[tuple[str, str], str] = {}
    for status_id, text in rows:
        report.scanned += 1
        for ticker, alias in find_tickers(text or "").items():
            wanted[(status_id, ticker)] = alias
            report.record(ticker)
    if not rows:
        return report

    scanned_ids = [r[0] for r in rows]
    async with db.session() as session, session.begin():
        stored: dict[tuple[str, str], str | None] = {}
        for chunk in _chunks(scanned_ids):
            result = await session.execute(
                select(StockMention.status_id, StockMention.ticker, StockMention.alias).where(
                    StockMention.status_id.in_(chunk)
                )
            )
            stored.update({(sid, t): alias for sid, t, alias in result})

        # A changed alias is rewritten too, so the audit column stays truthful.
        stale = [k for k, alias in stored.items() if wanted.get(k, _GONE) != alias]
        fresh = [k for k, alias in wanted.items() if stored.get(k, _GONE) != alias]

        repo = StockMentionRepository(session, db.dialect)
        for status_id, ticker in stale:
            await repo.delete(status_id, ticker)
        if fresh:
            await repo.insert_many(
                [{"status_id": s, "ticker": t, "alias": wanted[(s, t)]} for s, t in fresh]
            )
    report.added = len(fresh)
    report.removed = len(stale)
    return report


_GONE = object()  # sentinel: "no row", distinct from a stored NULL alias


def _chunks(items: Sequence[str], size: int = 1000) -> list[Sequence[str]]:
    """Split ``items`` so an IN (...) list stays well under driver parameter caps."""
    return [items[i : i + size] for i in range(0, len(items), size)]
