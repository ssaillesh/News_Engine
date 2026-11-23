"""Tests for the stock-mention detection pass.

The pass writes only the difference between what the matcher finds and what is
stored, so the cases that matter are the ones a naive diff gets wrong: a company
dropped from edited text, a status outside the scanned sources, and a re-run that
must write nothing.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from archiver.analysis.stocks import detect_mentions
from archiver.storage.models import StockMention
from archiver.storage.repositories import AccountRepository, StatusRepository

ACCOUNT = {"id": "news:acct", "username": "TrumpNews"}


async def _add_status(db, status_id: str, text: str, *, source: str = "news") -> None:
    async with db.session() as session, session.begin():
        await AccountRepository(session, db.dialect).upsert(dict(ACCOUNT))
        await StatusRepository(session, db.dialect).upsert(
            {
                "id": status_id,
                "account_id": ACCOUNT["id"],
                "created_at": datetime.now(UTC),
                "content_text": text,
                "content_hash": f"hash-of-{text}",
                "source": source,
            }
        )


async def _mentions(db) -> set[tuple[str, str]]:
    async with db.session() as session:
        rows = await session.execute(select(StockMention.status_id, StockMention.ticker))
        return {(s, t) for s, t in rows}


async def test_detects_and_persists(db):
    await _add_status(db, "news:1", "Apple and Nvidia rally")
    await _add_status(db, "news:2", "Trump posts on Truth Social")

    report = await detect_mentions(db)

    assert report.scanned == 2
    assert report.mentions == 3
    assert report.added == 3
    assert await _mentions(db) == {("news:1", "AAPL"), ("news:1", "NVDA"), ("news:2", "DJT")}


async def test_rerun_writes_nothing(db):
    await _add_status(db, "news:1", "Apple and Nvidia rally")
    await detect_mentions(db)

    again = await detect_mentions(db)

    # The report still describes the archive; only the stored diff is empty.
    assert again.mentions == 2
    assert (again.added, again.removed) == (0, 0)
    assert await _mentions(db) == {("news:1", "AAPL"), ("news:1", "NVDA")}


async def test_company_removed_from_text_is_dropped(db):
    await _add_status(db, "news:1", "Apple and Nvidia rally")
    await detect_mentions(db)

    await _add_status(db, "news:1", "Nvidia rallies alone")  # upsert: text edited
    report = await detect_mentions(db)

    assert (report.added, report.removed) == (0, 1)
    assert await _mentions(db) == {("news:1", "NVDA")}


async def test_leaves_unscanned_sources_alone(db):
    await _add_status(db, "fr:1", "Tariffs naming Apple", source="federal_register")
    async with db.session() as session, session.begin():
        session.add(StockMention(status_id="fr:1", ticker="AAPL", alias="Apple"))

    await detect_mentions(db)  # default sources exclude the Federal Register

    assert ("fr:1", "AAPL") in await _mentions(db)
