"""Normalization tests, including the row-dict ↔ ORM-column contract."""

from __future__ import annotations

from archiver.parsing import normalize_status, parse_status
from archiver.storage.models import Account, Media, Mention, Status, StatusMetric, Url


def test_normalize_simple(load_fixture):
    raw = load_fixture("status_simple.json")
    n = normalize_status(parse_status(raw), raw=raw)
    assert n.status["id"] == "111111111111111111"
    assert n.status["is_reblog"] is False
    assert n.status["content_text"] == "Hello world! This is a test."
    assert n.status["content_hash"] == n.content_hash
    assert n.status["raw"] is raw  # raw preserved for re-derivation
    assert n.account["id"] == "42"
    assert n.metric["reblogs_count"] == 5
    assert n.media == []


def test_normalize_media_mentions_tags_card(load_fixture):
    raw = load_fixture("status_with_media.json")
    n = normalize_status(parse_status(raw), raw=raw)
    assert len(n.media) == 1
    assert n.media[0]["id"] == "9001"
    assert n.media[0]["status_id"] == "222222222222222222"
    assert n.media[0]["meta"]["original"]["width"] == 1200
    assert n.mentions[0]["mentioned_account_id"] == "77"
    assert n.hashtags == ["news", "archive"]  # lowercased
    assert n.urls[0]["url"] == "https://example.com"
    assert n.urls[0]["provider_name"] == "example.com"
    assert n.status["in_reply_to_id"] == "111111111111111111"
    assert n.status["spoiler_text"] == "content warning"
    assert n.status["sensitive"] is True


def test_normalize_reblog_carries_original(load_fixture):
    raw = load_fixture("status_reblog.json")
    n = normalize_status(parse_status(raw), raw=raw)
    assert n.status["is_reblog"] is True
    assert n.status["reblog_of_id"] == "999999999999999999"
    assert n.reblog_of is not None
    assert n.reblog_of.status["id"] == "999999999999999999"
    assert "Original post" in n.reblog_of.status["content_text"]
    # the reblogged original has a different author
    assert n.reblog_of.account["id"] == "500"


def test_normalized_rows_construct_valid_orm_objects(load_fixture):
    """Proves normalizer output keys exactly match ORM columns (no DB needed).

    Constructing an ORM instance with an unknown kwarg raises TypeError, so this
    is a cheap contract test between Phase 4 output and the Phase 2 schema.
    """
    raw = load_fixture("status_with_media.json")
    n = normalize_status(parse_status(raw), raw=raw)
    Account(**n.account)
    Status(**n.status)
    StatusMetric(**n.metric)
    for media_row in n.media:
        Media(**media_row)
    for mention_row in n.mentions:
        Mention(**mention_row)
    for url_row in n.urls:
        Url(**url_row)
