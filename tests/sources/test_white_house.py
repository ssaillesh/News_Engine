"""Tests for the White House RSS source: parser, adapter, and ingest."""

from __future__ import annotations

from datetime import datetime

import httpx
import pytest
import respx
from sqlalchemy import func, select

from archiver.clients.rate_limit import NullRateLimiter
from archiver.config.settings import Settings
from archiver.sources.white_house import (
    WHITE_HOUSE_ACCOUNT,
    ingest_white_house,
    normalize_item,
    parse_feed,
)
from archiver.storage.db import Database
from archiver.storage.models import Status

_FEED_RE = r"https://www\.whitehouse\.gov/news/feed/.*"


@pytest.fixture
def settings() -> Settings:
    return Settings(env="test", user_agent="test-agent")


def test_parse_feed_extracts_items(load_text_fixture):
    items = parse_feed(load_text_fixture("wh_news_feed.xml"))
    assert len(items) == 2
    first = items[0]
    assert first["guid"].endswith("p=45462")
    assert first["categories"] == ["Briefings & Statements"]
    assert "Guam" in first["title"]
    assert "82nd anniversary" in first["content"]


def test_normalize_item(load_text_fixture):
    item = parse_feed(load_text_fixture("wh_news_feed.xml"))[0]
    account, status = normalize_item(item)
    assert account["id"] == WHITE_HOUSE_ACCOUNT["id"]
    assert status["id"] == "wh:45462"  # from the WordPress ?p= id
    assert status["source"] == "whitehouse"
    assert status["raw"]["category"] == "Briefings & Statements"
    assert isinstance(status["created_at"], datetime)
    assert status["created_at"].tzinfo is not None
    assert "liberation of Guam" in status["content_text"]


@respx.mock
async def test_ingest_persists_and_is_idempotent(settings, db: Database, load_text_fixture):
    xml = load_text_fixture("wh_news_feed.xml")
    respx.get(url__regex=_FEED_RE).mock(
        return_value=httpx.Response(200, text=xml, headers={"content-type": "application/rss+xml"})
    )

    n1 = await ingest_white_house(db, settings=settings, rate_limiter=NullRateLimiter())
    n2 = await ingest_white_house(db, settings=settings, rate_limiter=NullRateLimiter())
    assert n1 == 2
    assert n2 == 2  # processed again...

    async with db.session() as session:
        # ...but deduped in storage.
        assert await session.scalar(select(func.count()).select_from(Status)) == 2
        row = await session.get(Status, "wh:45502")
        assert row is not None
        assert row.source == "whitehouse"
        assert "$5 billion" in row.content_text
