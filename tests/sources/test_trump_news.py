"""Tests for the Trump news (Google News RSS) source, including the strict filter."""

from __future__ import annotations

import httpx
import pytest
import respx
from sqlalchemy import func, select

from archiver.clients.rate_limit import NullRateLimiter
from archiver.config.settings import Settings
from archiver.sources.trump_news import (
    _clean_title,
    build_google_news_url,
    ingest_news,
    mentions_keywords,
    normalize_news_item,
    parse_news_feed,
)
from archiver.storage.db import Database
from archiver.storage.models import Status

_NEWS_RE = r"https://news\.google\.com/rss/search.*"


@pytest.fixture
def settings() -> Settings:
    return Settings(env="test", user_agent="test-agent")


def test_build_url_encodes_query():
    url = build_google_news_url("Donald Trump")
    assert url.startswith("/rss/search?q=Donald+Trump")
    assert "ceid=US:en" in url


def test_clean_title_strips_publisher_suffix():
    # exact <source> match
    assert _clean_title("Big News - WSJ", "WSJ") == "Big News"
    # source name differs from the suffix (FT vs Financial Times) → generic fallback
    assert _clean_title("Is Trump winning? - Financial Times", "FT") == "Is Trump winning?"
    # no suffix → unchanged
    assert _clean_title("Trump signs order", "CNN") == "Trump signs order"


def test_parse_and_filter(load_text_fixture):
    items = parse_news_feed(load_text_fixture("google_news_trump.xml"))
    assert len(items) == 3
    kept = [i for i in items if mentions_keywords(i, ["trump"])]
    assert len(kept) == 2  # the weather item is filtered out
    assert all("trump" in (i["title"] or "").lower() for i in kept)


def test_normalize_strips_publisher_suffix_and_sets_kind(load_text_fixture):
    item = parse_news_feed(load_text_fixture("google_news_trump.xml"))[0]
    account, status = normalize_news_item(item)
    assert account["id"] == "news:donald-trump"
    assert status["source"] == "news"
    assert status["raw"]["kind"] == "WSJ"  # publisher → badge
    assert status["content_text"] == "Trump Approves Landmark Nuclear Deal With Saudi Arabia"
    assert status["id"] == "news:CBMiAAA111"


@respx.mock
async def test_ingest_keeps_only_trump_items(settings, db: Database, load_text_fixture):
    xml = load_text_fixture("google_news_trump.xml")
    respx.get(url__regex=_NEWS_RE).mock(
        return_value=httpx.Response(200, text=xml, headers={"content-type": "application/xml"})
    )

    n1 = await ingest_news(db, settings=settings, rate_limiter=NullRateLimiter())
    n2 = await ingest_news(db, settings=settings, rate_limiter=NullRateLimiter())
    assert n1 == 2  # weather item excluded
    assert n2 == 2

    async with db.session() as session:
        assert await session.scalar(select(func.count()).select_from(Status)) == 2  # deduped
        # nothing non-Trump slipped in
        rows = (await session.scalars(select(Status))).all()
        assert all("trump" in (r.content_text or r.raw.get("title", "")).lower() for r in rows)
