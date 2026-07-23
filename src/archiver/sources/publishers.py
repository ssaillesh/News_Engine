"""Publisher RSS ingester — Trump coverage *with* real summaries.

Why this exists alongside ``trump_news``: Google News RSS gives broad reach but
its ``<description>`` is only the headline repeated as a link, and its article
URLs are opaque redirects that never resolve to the publisher. Outlets' own feeds
carry a genuine publisher-written summary (and sometimes the full body in
``content:encoded``) plus a direct article link — which is exactly what a
"detailed summary" needs, obtained from feeds that exist to be syndicated.

Items land under ``source="news"`` so they share the "In the News" view and the
sentiment pass with Google News items. Each feed is fetched independently and a
failing outlet never aborts the run — one publisher changing their feed URL
should not cost you the other nineteen.
"""

from __future__ import annotations

import re
import unicodedata
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import TYPE_CHECKING, Any

from loguru import logger
from sqlalchemy import select

from archiver.clients.base import BaseHttpClient
from archiver.clients.exceptions import ClientError
from archiver.clients.rate_limit import RateLimiter, TokenBucket
from archiver.domain.hashing import content_hash, payload_hash
from archiver.parsing.rss import parse_rss
from archiver.parsing.text import html_to_text
from archiver.storage.models import Status
from archiver.storage.repositories import (
    AccountRepository,
    RawPayloadRepository,
    StatusRepository,
)

if TYPE_CHECKING:
    from archiver.config.settings import Settings
    from archiver.storage.db import Database

SOURCE = "news"
DEFAULT_KEYWORDS = ("trump",)

# Publisher → feed URL. Deliberately general-news feeds (politics/US) rather than
# Trump-specific ones: the keyword guard below does the filtering, and a general
# feed keeps working when an outlet retires a topic feed.
PUBLISHER_FEEDS: dict[str, str] = {
    "BBC": "https://feeds.bbci.co.uk/news/world/us_and_canada/rss.xml",
    "NPR": "https://feeds.npr.org/1001/rss.xml",
    "The Guardian": "https://www.theguardian.com/us-news/rss",
    "Politico": "https://rss.politico.com/politics-news.xml",
    "The Hill": "https://thehill.com/homenews/feed/",
    "Al Jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    "Sky News": "https://feeds.skynews.com/feeds/rss/world.xml",
    "CBS News": "https://www.cbsnews.com/latest/rss/politics",
    "NBC News": "https://feeds.nbcnews.com/nbcnews/public/politics",
    "CNBC": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000113",
    "Deutsche Welle": "https://rss.dw.com/rdf/rss-en-world",
    "France 24": "https://www.france24.com/en/america/rss",
}

PUBLISHERS_ACCOUNT: dict[str, Any] = {
    "id": "news:donald-trump",  # shared with trump_news: one "In the News" author
    "username": "TrumpNews",
    "acct": "donald-trump@news.google.com",
    "display_name": "Donald Trump — In the News",
    "url": "https://news.google.com/",
}

_WS_RE = re.compile(r"\s+")
_NONWORD_RE = re.compile(r"[^a-z0-9 ]+")
# Apostrophes are elided, not spaced: "Trump's" must key the same as "Trumps",
# which is how the other half of the press writes it.
_APOSTROPHE_RE = re.compile(r"['‘’ʼ]")


class PublisherClient(BaseHttpClient):
    """Fetches an absolute feed URL (each publisher is a different host)."""

    @classmethod
    def from_settings(
        cls, settings: Settings, *, rate_limiter: RateLimiter | None = None
    ) -> PublisherClient:
        return cls(
            "https://example.invalid",  # unused: every fetch passes an absolute URL
            user_agent=settings.user_agent,
            timeout_s=settings.http_timeout_s,
            max_retries=settings.http_max_retries,
            backoff_base_s=settings.backoff_base_s,
            backoff_cap_s=settings.backoff_cap_s,
            rate_limiter=rate_limiter or TokenBucket(settings.rate_limit_rps),
        )

    async def fetch_feed(self, url: str) -> str:
        return await self.get_text(url)


def mentions_keywords(item: dict[str, Any], keywords: Sequence[str]) -> bool:
    """True if title/description/body mentions any keyword (case-insensitive)."""
    haystack = " ".join(
        str(item.get(field) or "") for field in ("title", "description", "content")
    ).lower()
    return any(keyword.lower() in haystack for keyword in keywords)


def normalized_title(title: str) -> str:
    """A comparison key for spotting the same story from two feeds.

    Strips accents, punctuation, and case so "Trump's tariffs — explained" and
    "Trumps tariffs explained" collapse together. Deliberately conservative: it
    only catches near-identical headlines, not paraphrases, because wrongly
    merging two distinct stories is worse than keeping a duplicate.
    """
    deapostrophed = _APOSTROPHE_RE.sub("", title)
    folded = unicodedata.normalize("NFKD", deapostrophed).encode("ascii", "ignore").decode()
    return _WS_RE.sub(" ", _NONWORD_RE.sub(" ", folded.lower())).strip()


def _published_at(item: dict[str, Any]) -> datetime:
    raw = item.get("pub_date")
    if raw:
        try:
            when = parsedate_to_datetime(raw)
            return when.replace(tzinfo=UTC) if when.tzinfo is None else when
        except (TypeError, ValueError):
            try:  # Atom/ISO-8601 timestamps
                when = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                return when.replace(tzinfo=UTC) if when.tzinfo is None else when
            except ValueError:
                pass
    return datetime.now(UTC)


def _item_id(publisher: str, item: dict[str, Any]) -> str:
    key = item.get("guid") or item.get("link") or payload_hash(item)
    slug = _NONWORD_RE.sub("", publisher.lower().replace(" ", "-"))
    return f"pub:{slug}:{key}"


def normalize_publisher_item(
    publisher: str, item: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Map a publisher feed item into (account_row, status_row) dicts.

    ``content_text`` holds the summary rather than the headline — that is the
    whole point of this source, and it is what the dashboard renders under the
    title and what the summarizer condenses.
    """
    title = (item.get("title") or "").strip()
    body_html = item.get("content") or item.get("description")
    summary = html_to_text(body_html).strip()

    status_row = {
        "id": _item_id(publisher, item),
        "account_id": PUBLISHERS_ACCOUNT["id"],
        "created_at": _published_at(item),
        "url": item.get("link"),
        "uri": item.get("link"),
        "content_html": body_html,
        # Title first, then the summary: one text column that reads correctly in
        # search results and gives the UI a title/body split on the first newline.
        "content_text": f"{title}\n\n{summary}" if summary else title,
        "content_hash": content_hash(content=f"{title}\n\n{summary}"),
        "kind": publisher,
        "visibility": "public",
        "source": SOURCE,
        "raw": {**item, "publisher": publisher, "kind": publisher, "summary": summary},
    }
    return dict(PUBLISHERS_ACCOUNT), status_row


async def _existing_title_keys(db: Database) -> set[str]:
    """Normalized headlines already archived under ``source="news"``.

    Used to skip a story we already hold from Google News, so turning this source
    on does not double every headline in the feed.
    """
    async with db.session() as session:
        rows = (
            await session.scalars(select(Status.content_text).where(Status.source == SOURCE))
        ).all()
    keys = set()
    for text in rows:
        if text:
            keys.add(normalized_title(text.split("\n", 1)[0]))
    return keys


async def ingest_publishers(
    db: Database,
    *,
    settings: Settings,
    feeds: dict[str, str] | None = None,
    keywords: Sequence[str] = DEFAULT_KEYWORDS,
    skip_duplicate_titles: bool = True,
    rate_limiter: RateLimiter | None = None,
) -> int:
    """Fetch publisher feeds and upsert Trump items that carry a summary.

    Idempotent (guid-keyed upsert + raw-hash dedup). Returns items kept.
    """
    registry = feeds if feeds is not None else PUBLISHER_FEEDS
    seen = await _existing_title_keys(db) if skip_duplicate_titles else set()
    processed = 0

    async with PublisherClient.from_settings(settings, rate_limiter=rate_limiter) as client:
        for publisher, url in registry.items():
            try:
                xml_text = await client.fetch_feed(url)
                items = parse_rss(xml_text)
            except (ClientError, ET.ParseError) as exc:
                # One broken feed must not cost us the rest of the run.
                logger.warning("publisher feed failed: {} ({}): {}", publisher, url, exc)
                continue

            for item in items:
                if not mentions_keywords(item, keywords):
                    continue
                account_row, status_row = normalize_publisher_item(publisher, item)
                key = normalized_title(str(item.get("title") or ""))
                if skip_duplicate_titles and key and key in seen:
                    continue
                seen.add(key)

                async with db.session() as session, session.begin():
                    await AccountRepository(session, db.dialect).upsert(account_row)
                    await StatusRepository(session, db.dialect).upsert(status_row)
                    await RawPayloadRepository(session, db.dialect).save(
                        {
                            "endpoint": url,
                            "entity_type": "publisher_article",
                            "entity_id": status_row["id"],
                            "payload": status_row["raw"],
                            "payload_sha256": payload_hash(status_row["raw"]),
                        }
                    )
                processed += 1
    return processed
