"""Version-tolerant Pydantic schemas mirroring the Mastodon API JSON.

``extra="ignore"`` means unknown/new upstream fields are dropped rather than
raising (the full raw payload is preserved separately in ``raw_payloads``), and
almost everything is optional with a sensible default so a missing field never
breaks ingestion. Only the genuinely load-bearing fields are required.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore")


class AccountSchema(_Base):
    id: str
    username: str
    acct: str | None = None
    display_name: str | None = None
    url: str | None = None
    created_at: datetime | None = None
    note: str | None = None
    followers_count: int | None = None
    following_count: int | None = None
    statuses_count: int | None = None
    avatar_static: str | None = None
    header_static: str | None = None


class MediaAttachmentSchema(_Base):
    id: str
    type: str | None = None
    url: str | None = None
    preview_url: str | None = None
    remote_url: str | None = None
    description: str | None = None
    blurhash: str | None = None
    meta: dict[str, Any] | None = None


class MentionSchema(_Base):
    id: str | None = None
    username: str | None = None
    acct: str | None = None
    url: str | None = None


class TagSchema(_Base):
    name: str
    url: str | None = None


class CardSchema(_Base):
    url: str | None = None
    title: str | None = None
    description: str | None = None
    provider_name: str | None = None
    image: str | None = None


class PollOptionSchema(_Base):
    title: str
    votes_count: int | None = None


class PollSchema(_Base):
    id: str | None = None
    options: list[PollOptionSchema] = Field(default_factory=list)


class StatusSchema(_Base):
    id: str
    created_at: datetime
    edited_at: datetime | None = None
    url: str | None = None
    uri: str | None = None
    content: str = ""
    language: str | None = None
    visibility: str | None = None
    sensitive: bool = False
    spoiler_text: str = ""
    in_reply_to_id: str | None = None
    in_reply_to_account_id: str | None = None
    replies_count: int | None = None
    reblogs_count: int | None = None
    favourites_count: int | None = None
    account: AccountSchema
    reblog: StatusSchema | None = None
    media_attachments: list[MediaAttachmentSchema] = Field(default_factory=list)
    mentions: list[MentionSchema] = Field(default_factory=list)
    tags: list[TagSchema] = Field(default_factory=list)
    card: CardSchema | None = None
    poll: PollSchema | None = None


class ContextSchema(_Base):
    ancestors: list[StatusSchema] = Field(default_factory=list)
    descendants: list[StatusSchema] = Field(default_factory=list)


# Resolve the self-referential StatusSchema.reblog forward reference.
StatusSchema.model_rebuild()


def parse_status(raw: dict[str, Any]) -> StatusSchema:
    return StatusSchema.model_validate(raw)


def parse_account(raw: dict[str, Any]) -> AccountSchema:
    return AccountSchema.model_validate(raw)


def parse_context(raw: dict[str, Any]) -> ContextSchema:
    return ContextSchema.model_validate(raw)
