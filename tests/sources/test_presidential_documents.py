"""Tests for the Compilation of Presidential Documents (GovInfo CPD) source."""

from __future__ import annotations

from datetime import datetime

import httpx
import pytest
import respx
from sqlalchemy import func, select

from archiver.clients.rate_limit import NullRateLimiter
from archiver.config.settings import Settings
from archiver.sources.presidential_documents import (
    TRUMP_ACCOUNT,
    ingest_presidential_documents,
    normalize_package,
)
from archiver.storage.db import Database
from archiver.storage.models import Status

_PUB_RE = r"https://api\.govinfo\.gov/published/.*"


@pytest.fixture
def settings() -> Settings:
    return Settings(env="test", user_agent="test-agent", govinfo_api_key="DEMO_KEY")


def test_normalize_package_derives_kind(load_fixture):
    packages = load_fixture("cpd_published.json")["packages"]
    account, remarks = normalize_package(packages[0])
    assert account["id"] == TRUMP_ACCOUNT["id"]
    assert remarks["id"] == "cpd:DCPD-202600445"
    assert remarks["source"] == "presidential_documents"
    assert remarks["raw"]["kind"] == "Remarks"
    assert remarks["url"].endswith("DCPD-202600445")
    assert isinstance(remarks["created_at"], datetime)

    _account, message = normalize_package(packages[1])
    assert message["raw"]["kind"] == "Message"


@respx.mock
async def test_ingest_paginates_and_is_idempotent(settings, db: Database, load_fixture):
    page1 = load_fixture("cpd_published.json")
    page2 = {"count": 3, "packages": [
        {"packageId": "DCPD-202600460", "title": "Statement on the Economy",
         "dateIssued": "2026-06-08", "docClass": "DCPD"}
    ], "nextPage": None}

    respx.get(url__regex=_PUB_RE).mock(
        side_effect=[
            httpx.Response(200, json=page1),
            httpx.Response(200, json=page2),
            httpx.Response(200, json=page1),  # second run
            httpx.Response(200, json=page2),
        ]
    )

    n1 = await ingest_presidential_documents(
        db, settings=settings, since="2026-06-01", rate_limiter=NullRateLimiter()
    )
    assert n1 == 3  # 2 from page1 + 1 from page2

    await ingest_presidential_documents(
        db, settings=settings, since="2026-06-01", rate_limiter=NullRateLimiter()
    )
    async with db.session() as session:
        assert await session.scalar(select(func.count()).select_from(Status)) == 3  # deduped
        row = await session.get(Status, "cpd:DCPD-202600445")
        assert row is not None
        assert row.source == "presidential_documents"
        assert "Coal" in row.content_text
