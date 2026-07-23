"""Normalize validated schemas into storage-ready row dicts (DESIGN.md §8).

The output keys match the ORM column names in ``archiver.storage.models`` exactly,
so a ``NormalizedStatus`` can be persisted directly by the Phase 2 repositories.
Volatile counts are split into ``metric`` (a time-series row), content-defining
fields are hashed for dedup/edit detection, and reblogs carry a normalized copy of
the original status (which must be persisted first to satisfy the self-FK).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from archiver.domain.hashing import content_hash
from archiver.parsing.media import extract_media
from archiver.parsing.schemas import AccountSchema, StatusSchema
from archiver.parsing.text import html_to_text


@dataclass(slots=True)
class NormalizedStatus:
    """Storage-ready projection of one status and its related rows."""

    account: dict[str, Any]
    status: dict[str, Any]
    metric: dict[str, Any]
    media: list[dict[str, Any]]
    mentions: list[dict[str, Any]]
    hashtags: list[str]
    urls: list[dict[str, Any]]
    content_hash: str
    reblog_of: NormalizedStatus | None = field(default=None)


def normalize_account(
    account: AccountSchema, *, raw: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Project an account into an ``accounts``-row dict."""
    return {
        "id": account.id,
        "username": account.username,
        "acct": account.acct,
        "display_name": account.display_name,
        "url": account.url,
        "created_at": account.created_at,
        "raw": raw,
    }


def normalize_status(
    status: StatusSchema, *, raw: dict[str, Any] | None = None
) -> NormalizedStatus:
    """Project a status (and any reblogged original) into storage-ready rows."""
    reblog_of: NormalizedStatus | None = None
    if status.reblog is not None:
        reblog_raw = raw.get("reblog") if isinstance(raw, dict) else None
        reblog_of = normalize_status(status.reblog, raw=reblog_raw)

    media = extract_media(status)
    media_ids = [m["id"] for m in media]
    poll_options = [opt.title for opt in status.poll.options] if status.poll else None
    chash = content_hash(
        content=status.content,
        spoiler_text=status.spoiler_text,
        sensitive=status.sensitive,
        media_ids=media_ids,
        poll_options=poll_options,
    )

    account_raw = raw.get("account") if isinstance(raw, dict) else None
    status_row = {
        "id": status.id,
        "account_id": status.account.id,
        "created_at": status.created_at,
        "edited_at": status.edited_at,
        "url": status.url,
        "uri": status.uri,
        "in_reply_to_id": status.in_reply_to_id,
        "in_reply_to_account_id": status.in_reply_to_account_id,
        "reblog_of_id": status.reblog.id if status.reblog else None,
        "is_reblog": status.reblog is not None,
        "visibility": status.visibility,
        "sensitive": status.sensitive,
        "spoiler_text": status.spoiler_text or None,
        "language": status.language,
        "content_html": status.content or None,
        "content_text": html_to_text(status.content) or None,
        "content_hash": chash,
        "raw": raw,
    }
    metric = {
        "status_id": status.id,
        "replies_count": status.replies_count,
        "reblogs_count": status.reblogs_count,
        "favourites_count": status.favourites_count,
    }
    mentions = [
        {
            "status_id": status.id,
            "mentioned_account_id": mention.id,
            "username": mention.username,
            "acct": mention.acct,
            "url": mention.url,
        }
        for mention in status.mentions
    ]
    hashtags = [tag.name.lower() for tag in status.tags]
    urls: list[dict[str, Any]] = []
    if status.card is not None and status.card.url:
        urls.append(
            {
                "status_id": status.id,
                "url": status.card.url,
                "title": status.card.title,
                "description": status.card.description,
                "provider_name": status.card.provider_name,
                "image_url": status.card.image,
            }
        )

    return NormalizedStatus(
        account=normalize_account(status.account, raw=account_raw),
        status=status_row,
        metric=metric,
        media=media,
        mentions=mentions,
        hashtags=hashtags,
        urls=urls,
        content_hash=chash,
        reblog_of=reblog_of,
    )
