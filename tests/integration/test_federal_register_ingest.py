"""End-to-end Federal Register ingest test (respx-mocked API + real DB).

Verifies pagination via ``next_page_url``, persistence into the archive, and
idempotency across repeated runs (no duplicate statuses or raw payloads).
"""

from __future__ import annotations

import httpx
import pytest
import respx
from sqlalchemy import func, select

from archiver.clients.rate_limit import NullRateLimiter
from archiver.config.settings import Settings
from archiver.sources.federal_register import TRUMP_ACCOUNT, ingest_federal_register
from archiver.storage.db import Database
from archiver.storage.models import CheckpointState, RawPayload, Status

_DOCS_RE = r"https://www\.federalregister\.gov/api/v1/documents(\.json)?.*"


def _doc(number: str, title: str, date: str = "2026-07-17") -> dict:
    return {
        "document_number": number,
        "title": title,
        "type": "Presidential Document",
        "subtype": "Executive Order",
        "publication_date": date,
        "html_url": f"https://www.federalregister.gov/documents/2026/07/17/{number}/x",
    }


def _page(docs: list[dict], next_url: str | None) -> httpx.Response:
    return httpx.Response(200, json={"results": docs, "next_page_url": next_url})


@pytest.fixture
def settings() -> Settings:
    return Settings(env="test", user_agent="test-agent")


@respx.mock
async def test_ingest_paginates_and_persists(settings, db: Database):
    page2_url = "https://www.federalregister.gov/api/v1/documents?page=2&format=json"
    respx.get(url__regex=_DOCS_RE).mock(
        side_effect=[
            _page([_doc("2026-1", "First EO"), _doc("2026-2", "Second EO")], page2_url),
            _page([_doc("2026-3", "Third EO")], None),
        ]
    )

    count = await ingest_federal_register(db, settings=settings, rate_limiter=NullRateLimiter())
    assert count == 3

    async with db.session() as session:
        assert await session.scalar(select(func.count()).select_from(Status)) == 3
        row = await session.get(Status, "fr:2026-1")
        assert row is not None
        assert row.source == "federal_register"
        assert row.content_text.startswith("[Executive Order] First EO")


@respx.mock
async def test_ingest_is_idempotent(settings, db: Database):
    page2_url = "https://www.federalregister.gov/api/v1/documents?page=2&format=json"
    # Enough responses for two full runs.
    respx.get(url__regex=_DOCS_RE).mock(
        side_effect=[
            _page([_doc("2026-1", "First EO"), _doc("2026-2", "Second EO")], page2_url),
            _page([_doc("2026-3", "Third EO")], None),
            _page([_doc("2026-1", "First EO"), _doc("2026-2", "Second EO")], page2_url),
            _page([_doc("2026-3", "Third EO")], None),
        ]
    )

    await ingest_federal_register(db, settings=settings, rate_limiter=NullRateLimiter())
    await ingest_federal_register(db, settings=settings, rate_limiter=NullRateLimiter())

    async with db.session() as session:
        assert await session.scalar(select(func.count()).select_from(Status)) == 3
        assert await session.scalar(select(func.count()).select_from(RawPayload)) == 3


@respx.mock
async def test_incremental_sets_and_uses_checkpoint(settings, db: Database):
    route = respx.get(url__regex=_DOCS_RE).mock(
        side_effect=[
            _page(
                [
                    _doc("2026-9", "Newer", date="2026-07-20"),
                    _doc("2026-8", "Older", date="2026-07-18"),
                ],
                None,
            ),
            _page([], None),  # second run: API returns nothing new
        ]
    )

    n1 = await ingest_federal_register(
        db, settings=settings, rate_limiter=NullRateLimiter(), incremental=True
    )
    assert n1 == 2

    async with db.session() as session:
        checkpoint = await session.get(CheckpointState, TRUMP_ACCOUNT["id"])
        assert checkpoint is not None
        assert checkpoint.frontier_cursor == "2026-07-20"  # latest publication_date

    n2 = await ingest_federal_register(
        db, settings=settings, rate_limiter=NullRateLimiter(), incremental=True
    )
    assert n2 == 0
    # the second run must have asked the API only for docs on/after the checkpoint
    last_request = route.calls[-1].request
    assert last_request.url.params.get("conditions[publication_date][gte]") == "2026-07-20"
