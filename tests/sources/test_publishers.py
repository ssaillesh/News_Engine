"""Tests for the publisher-RSS ingester."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from archiver.config.settings import Settings
from archiver.sources.publishers import (
    ingest_publishers,
    mentions_keywords,
    normalize_publisher_item,
    normalized_title,
)
from archiver.storage.db import Database
from archiver.storage.models import Status

FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>Example News</title>
  <item>
    <title>Trump signs sweeping tariff order</title>
    <link>https://example.com/a</link>
    <guid>https://example.com/a</guid>
    <pubDate>Wed, 22 Jul 2026 10:00:00 GMT</pubDate>
    <description>&lt;p&gt;The order raises duties on imports and drew
      immediate criticism from trading partners.&lt;/p&gt;</description>
  </item>
  <item>
    <title>Local bakery wins award</title>
    <link>https://example.com/b</link>
    <guid>https://example.com/b</guid>
    <pubDate>Wed, 22 Jul 2026 09:00:00 GMT</pubDate>
    <description>Nothing political here.</description>
  </item>
</channel></rss>
"""


@pytest.fixture
def settings() -> Settings:
    return Settings(env="test", rate_limit_rps=1000)


def _items(xml: str = FEED):
    from archiver.parsing.rss import parse_rss

    return parse_rss(xml)


# ── filtering ─────────────────────────────────────────────────────────────────
def test_keyword_guard_keeps_only_trump_items():
    kept = [i for i in _items() if mentions_keywords(i, ["trump"])]
    assert [i["title"] for i in kept] == ["Trump signs sweeping tariff order"]


def test_keyword_guard_matches_body_not_just_title():
    item = {"title": "Tariffs rise", "description": "President Trump signed the order."}
    assert mentions_keywords(item, ["trump"])


# ── normalization ─────────────────────────────────────────────────────────────
def test_normalize_puts_summary_in_content_text():
    account, status = normalize_publisher_item("BBC", _items()[0])

    assert account["id"] == "news:donald-trump"
    assert status["kind"] == "BBC"
    assert status["source"] == "news"
    assert status["url"] == "https://example.com/a"
    title, body = status["content_text"].split("\n\n", 1)
    assert title == "Trump signs sweeping tariff order"
    assert "raises duties on imports" in body, "the publisher summary must be captured"


def test_normalize_survives_a_missing_description():
    _, status = normalize_publisher_item("BBC", {"title": "Trump speaks", "link": "u"})
    assert status["content_text"] == "Trump speaks"


# ── duplicate detection ───────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("Trump's tariffs — explained", "Trumps tariffs explained"),
        ("TRUMP SIGNS ORDER", "Trump signs order"),
        ("Trump  signs   order", "Trump signs order"),
    ],
)
def test_normalized_title_collapses_near_identical_headlines(left, right):
    assert normalized_title(left) == normalized_title(right)


def test_normalized_title_keeps_distinct_stories_apart():
    assert normalized_title("Trump signs order") != normalized_title("Trump vetoes order")


# ── ingest ────────────────────────────────────────────────────────────────────
async def test_ingest_persists_only_trump_items(settings, db: Database, respx_mock):
    import httpx

    respx_mock.get("https://x.test/feed").mock(return_value=httpx.Response(200, text=FEED))

    count = await ingest_publishers(db, settings=settings, feeds={"Example": "https://x.test/feed"})

    assert count == 1
    async with db.session() as session:
        rows = (await session.scalars(select(Status))).all()
    assert len(rows) == 1
    assert rows[0].kind == "Example"
    assert "raises duties on imports" in rows[0].content_text


async def test_ingest_is_idempotent(settings, db: Database, respx_mock):
    import httpx

    respx_mock.get("https://x.test/feed").mock(return_value=httpx.Response(200, text=FEED))
    feeds = {"Example": "https://x.test/feed"}

    await ingest_publishers(db, settings=settings, feeds=feeds)
    await ingest_publishers(db, settings=settings, feeds=feeds)

    async with db.session() as session:
        rows = (await session.scalars(select(Status))).all()
    assert len(rows) == 1, "re-running must not duplicate"


async def test_ingest_skips_headlines_already_archived(settings, db: Database, respx_mock):
    import httpx

    respx_mock.get("https://x.test/feed").mock(return_value=httpx.Response(200, text=FEED))
    respx_mock.get("https://y.test/feed").mock(return_value=httpx.Response(200, text=FEED))

    await ingest_publishers(db, settings=settings, feeds={"First": "https://x.test/feed"})
    # A second outlet carrying the same story must not double it up.
    count = await ingest_publishers(db, settings=settings, feeds={"Second": "https://y.test/feed"})

    assert count == 0


async def test_allow_duplicates_keeps_both_copies(settings, db: Database, respx_mock):
    import httpx

    respx_mock.get("https://x.test/feed").mock(return_value=httpx.Response(200, text=FEED))
    respx_mock.get("https://y.test/feed").mock(return_value=httpx.Response(200, text=FEED))

    await ingest_publishers(db, settings=settings, feeds={"First": "https://x.test/feed"})
    count = await ingest_publishers(
        db,
        settings=settings,
        feeds={"Second": "https://y.test/feed"},
        skip_duplicate_titles=False,
    )

    assert count == 1


async def test_one_broken_feed_does_not_abort_the_run(settings, db: Database, respx_mock):
    import httpx

    respx_mock.get("https://bad.test/feed").mock(return_value=httpx.Response(500))
    respx_mock.get("https://ok.test/feed").mock(return_value=httpx.Response(200, text=FEED))

    count = await ingest_publishers(
        db,
        settings=settings,
        feeds={"Broken": "https://bad.test/feed", "Working": "https://ok.test/feed"},
    )

    assert count == 1, "a failing publisher must not cost us the working ones"


async def test_malformed_xml_is_survived(settings, db: Database, respx_mock):
    import httpx

    respx_mock.get("https://bad.test/feed").mock(
        return_value=httpx.Response(200, text="<rss><channel>truncated")
    )
    respx_mock.get("https://ok.test/feed").mock(return_value=httpx.Response(200, text=FEED))

    count = await ingest_publishers(
        db,
        settings=settings,
        feeds={"Broken": "https://bad.test/feed", "Working": "https://ok.test/feed"},
    )

    assert count == 1
