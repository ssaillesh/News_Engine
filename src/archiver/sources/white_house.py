"""White House ingester — official statements, releases, and messages via RSS.

whitehouse.gov publishes its news as RSS feeds (``/news/feed/``,
``/presidential-actions/feed/``). Its robots.txt allows crawling and the feeds are
proper ``application/rss+xml`` — a clean, structured, compliant source of official
communications during the administration. Parsed with the standard library (no
extra deps).

RSS carries only the most recent ~30 items, so this is a *monitor-latest* source:
run it on a schedule to accumulate new items over time (older items age out of the
feed). Idempotent — re-running never duplicates.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import TYPE_CHECKING, Any

from archiver.clients.base import BaseHttpClient
from archiver.clients.rate_limit import RateLimiter, TokenBucket
from archiver.domain.hashing import content_hash, payload_hash
from archiver.parsing.text import html_to_text
from archiver.storage.repositories import (
    AccountRepository,
    RawPayloadRepository,
    StatusRepository,
)

if TYPE_CHECKING:
    from archiver.config.settings import Settings
    from archiver.storage.db import Database

SOURCE = "whitehouse"
DEFAULT_FEEDS = ("/news/feed/",)

_CONTENT_NS = "http://purl.org/rss/1.0/modules/content/"
_DC_NS = "http://purl.org/dc/elements/1.1/"
_WP_ID_RE = re.compile(r"[?&]p=(\d+)")

WHITE_HOUSE_ACCOUNT: dict[str, Any] = {
    "id": "wh:white-house",
    "username": "WhiteHouse",
    "acct": "whitehouse@whitehouse.gov",
    "display_name": "The White House",
    "url": "https://www.whitehouse.gov/",
}


class WhiteHouseClient(BaseHttpClient):
    BASE_URL = "https://www.whitehouse.gov"

    @classmethod
    def from_settings(
        cls, settings: Settings, *, rate_limiter: RateLimiter | None = None
    ) -> WhiteHouseClient:
        return cls(
            cls.BASE_URL,
            user_agent=settings.user_agent,
            timeout_s=settings.http_timeout_s,
            max_retries=settings.http_max_retries,
            backoff_base_s=settings.backoff_base_s,
            backoff_cap_s=settings.backoff_cap_s,
            rate_limiter=rate_limiter or TokenBucket(settings.rate_limit_rps),
        )

    async def fetch_feed(self, path: str) -> str:
        return await self.get_text(path)


def parse_feed(xml_text: str) -> list[dict[str, Any]]:
    """Parse an RSS feed into a list of item dicts (stdlib only)."""
    root = ET.fromstring(xml_text)
    channel = root.find("channel")
    if channel is None:
        return []
    items: list[dict[str, Any]] = []
    for item in channel.findall("item"):
        items.append(
            {
                "guid": item.findtext("guid"),
                "title": (item.findtext("title") or "").strip(),
                "link": item.findtext("link"),
                "pub_date": item.findtext("pubDate"),
                "categories": [c.text for c in item.findall("category") if c.text],
                "creator": item.findtext(f"{{{_DC_NS}}}creator"),
                "description": item.findtext("description"),
                "content": item.findtext(f"{{{_CONTENT_NS}}}encoded"),
            }
        )
    return items


def _post_id(item: dict[str, Any]) -> str:
    guid = item.get("guid") or ""
    match = _WP_ID_RE.search(guid)
    if match:
        return match.group(1)
    link = item.get("link") or guid
    if link:
        tail = link.rstrip("/").rsplit("/", 1)[-1]
        if tail:
            return tail
    return payload_hash(item)[:16]


def _published_at(item: dict[str, Any]) -> datetime:
    raw = item.get("pub_date")
    if raw:
        try:
            when = parsedate_to_datetime(raw)
            return when.replace(tzinfo=UTC) if when.tzinfo is None else when
        except (TypeError, ValueError):
            pass
    return datetime.now(UTC)


def normalize_item(item: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Map an RSS item into (account_row, status_row) dicts."""
    post_id = _post_id(item)
    content_html = item.get("content") or item.get("description")
    content_text = html_to_text(content_html)
    title = item.get("title") or (content_text.split("\n", 1)[0] if content_text else post_id)
    categories = item.get("categories") or []

    category = categories[0] if categories else "White House"
    raw = {**item, "category": category}
    status_row = {
        "id": f"wh:{post_id}",
        "account_id": WHITE_HOUSE_ACCOUNT["id"],
        "created_at": _published_at(item),
        "url": item.get("link"),
        "uri": item.get("link"),
        "content_html": content_html,
        "content_text": content_text or title,
        "content_hash": content_hash(content=content_text or title),
        "kind": category,
        "visibility": "public",
        "source": SOURCE,
        "raw": raw,
    }
    return dict(WHITE_HOUSE_ACCOUNT), status_row


async def ingest_white_house(
    db: Database,
    *,
    settings: Settings,
    feeds: Sequence[str] = DEFAULT_FEEDS,
    rate_limiter: RateLimiter | None = None,
) -> int:
    """Fetch White House RSS feed(s) and upsert items into the archive.

    Idempotent (guid-keyed upsert + raw-hash dedup). Returns items processed.
    """
    processed = 0
    async with WhiteHouseClient.from_settings(settings, rate_limiter=rate_limiter) as client:
        for feed_path in feeds:
            xml_text = await client.fetch_feed(feed_path)
            for item in parse_feed(xml_text):
                account_row, status_row = normalize_item(item)
                async with db.session() as session, session.begin():
                    await AccountRepository(session, db.dialect).upsert(account_row)
                    await StatusRepository(session, db.dialect).upsert(status_row)
                    await RawPayloadRepository(session, db.dialect).save(
                        {
                            "endpoint": f"whitehouse{feed_path}",
                            "entity_type": "whitehouse_news",
                            "entity_id": status_row["id"],
                            "payload": status_row["raw"],
                            "payload_sha256": payload_hash(status_row["raw"]),
                        }
                    )
                processed += 1
    return processed
