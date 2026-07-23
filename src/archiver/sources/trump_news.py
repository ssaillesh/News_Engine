"""Trump news ingester — coverage *about* Donald Trump via Google News RSS.

Google News exposes an RSS search feed for any query. We query "Donald Trump" and
then apply a keyword guard so only items that actually mention Trump are kept —
"specifically Donald Trump". This is third-party *coverage* (distinct from the
first-party sources), stored under ``source="news"`` with the publisher as the
badge. Google News RSS is a public syndication feed; items link back to publishers.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import quote_plus

from archiver.clients.base import BaseHttpClient
from archiver.clients.rate_limit import RateLimiter, TokenBucket
from archiver.domain.hashing import content_hash, payload_hash
from archiver.storage.repositories import (
    AccountRepository,
    RawPayloadRepository,
    StatusRepository,
)

if TYPE_CHECKING:
    from archiver.config.settings import Settings
    from archiver.storage.db import Database

SOURCE = "news"
DEFAULT_QUERY = "Donald Trump"
DEFAULT_KEYWORDS = ("trump",)  # item must mention this to be kept (Donald-specific guard)

NEWS_ACCOUNT: dict[str, Any] = {
    "id": "news:donald-trump",
    "username": "TrumpNews",
    "acct": "donald-trump@news.google.com",
    "display_name": "Donald Trump — In the News",
    "url": "https://news.google.com/",
}


def build_google_news_url(query: str) -> str:
    """Build the Google News RSS search path for a query (US English)."""
    return f"/rss/search?q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"


class NewsClient(BaseHttpClient):
    BASE_URL = "https://news.google.com"

    @classmethod
    def from_settings(
        cls, settings: Settings, *, rate_limiter: RateLimiter | None = None
    ) -> NewsClient:
        return cls(
            cls.BASE_URL,
            user_agent=settings.user_agent,
            timeout_s=settings.http_timeout_s,
            max_retries=settings.http_max_retries,
            backoff_base_s=settings.backoff_base_s,
            backoff_cap_s=settings.backoff_cap_s,
            rate_limiter=rate_limiter or TokenBucket(settings.rate_limit_rps),
        )

    async def fetch(self, path: str) -> str:
        return await self.get_text(path)


def parse_news_feed(xml_text: str) -> list[dict[str, Any]]:
    """Parse a Google News RSS feed into item dicts (title, link, publisher, …)."""
    root = ET.fromstring(xml_text)
    channel = root.find("channel")
    if channel is None:
        return []
    items: list[dict[str, Any]] = []
    for item in channel.findall("item"):
        source_el = item.find("source")
        items.append(
            {
                "guid": item.findtext("guid"),
                "title": (item.findtext("title") or "").strip(),
                "link": item.findtext("link"),
                "pub_date": item.findtext("pubDate"),
                "description": item.findtext("description"),
                "publisher": source_el.text if source_el is not None else None,
                "publisher_url": source_el.get("url") if source_el is not None else None,
            }
        )
    return items


def mentions_keywords(item: dict[str, Any], keywords: Sequence[str]) -> bool:
    """True if the item's title/description mentions any keyword (case-insensitive)."""
    haystack = f"{item.get('title') or ''} {item.get('description') or ''}".lower()
    return any(keyword.lower() in haystack for keyword in keywords)


def _published_at(item: dict[str, Any]) -> datetime:
    raw = item.get("pub_date")
    if raw:
        try:
            when = parsedate_to_datetime(raw)
            return when.replace(tzinfo=UTC) if when.tzinfo is None else when
        except (TypeError, ValueError):
            pass
    return datetime.now(UTC)


# A trailing " - Publisher" segment (short, no interior hyphen) that Google News appends.
_TRAILING_SOURCE = re.compile(r"\s+-\s+[^-\n]{1,40}$")


def _clean_title(title: str, publisher: str | None) -> str:
    """Strip the trailing ' - Publisher' that Google News appends to titles.

    Prefers the exact ``<source>`` name; falls back to a generic trailing-source
    pattern for the cases where Google's source name differs from the suffix
    (e.g. source "FT" vs. title "… - Financial Times").
    """
    if publisher and title.endswith(f" - {publisher}"):
        return title[: -len(f" - {publisher}")].strip()
    return _TRAILING_SOURCE.sub("", title).strip() or title


def normalize_news_item(item: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Map a news item into (account_row, status_row) dicts."""
    guid = item.get("guid") or item.get("link") or payload_hash(item)
    publisher = item.get("publisher") or "News"
    title = _clean_title(item.get("title") or "", publisher)

    status_row = {
        "id": f"news:{guid}",
        "account_id": NEWS_ACCOUNT["id"],
        "created_at": _published_at(item),
        "url": item.get("link"),
        "uri": item.get("link"),
        "content_html": item.get("description"),
        "content_text": title,
        "content_hash": content_hash(content=title),
        "kind": publisher,
        "visibility": "public",
        "source": SOURCE,
        "raw": {**item, "kind": publisher},
    }
    return dict(NEWS_ACCOUNT), status_row


async def ingest_news(
    db: Database,
    *,
    settings: Settings,
    query: str = DEFAULT_QUERY,
    keywords: Sequence[str] = DEFAULT_KEYWORDS,
    rate_limiter: RateLimiter | None = None,
) -> int:
    """Fetch Google News RSS for ``query`` and upsert items that mention ``keywords``.

    Idempotent (guid-keyed upsert + raw-hash dedup). Returns items kept.
    """
    path = build_google_news_url(query)
    processed = 0
    async with NewsClient.from_settings(settings, rate_limiter=rate_limiter) as client:
        xml_text = await client.fetch(path)
        for item in parse_news_feed(xml_text):
            if not mentions_keywords(item, keywords):
                continue  # strict Donald-Trump guard
            account_row, status_row = normalize_news_item(item)
            async with db.session() as session, session.begin():
                await AccountRepository(session, db.dialect).upsert(account_row)
                await StatusRepository(session, db.dialect).upsert(status_row)
                await RawPayloadRepository(session, db.dialect).save(
                    {
                        "endpoint": "google_news/rss/search",
                        "entity_type": "news_article",
                        "entity_id": status_row["id"],
                        "payload": status_row["raw"],
                        "payload_sha256": payload_hash(status_row["raw"]),
                    }
                )
            processed += 1
    return processed
