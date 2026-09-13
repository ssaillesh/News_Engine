"""SQLAlchemy 2.0 ORM models — the normalized archive schema (DESIGN.md §6).

Portability notes:
  * ``JSONType`` renders as ``JSONB`` on PostgreSQL and generic ``JSON`` elsewhere.
  * Timestamps are timezone-aware (``TIMESTAMPTZ`` on Postgres) and stored in UTC.
  * Postgres-only optimizations (GIN indexes, range partitioning) are deliberately
    deferred to later migrations, as noted in DESIGN.md §6/§14 — the base schema is
    kept portable so it can also run on SQLite for tests and the minimal profile.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Double,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# JSON on SQLite, JSONB on PostgreSQL — one declaration, two backends.
JSONType = JSON().with_variant(JSONB(), "postgresql")

# Auto-incrementing surrogate primary keys: BIGINT on Postgres, but INTEGER on
# SQLite because SQLite only auto-increments an INTEGER PRIMARY KEY (rowid alias),
# not BIGINT. One declaration keeps the schema portable across both backends.
BigIntPK = BigInteger().with_variant(Integer, "sqlite")

# Deterministic constraint/index names so Alembic autogenerate stays stable.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)


def utcnow() -> datetime:
    """Timezone-aware current time in UTC (default for capture timestamps)."""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    metadata = metadata


# Reusable column type aliases.
_TS = DateTime(timezone=True)


# ─────────────────────────────────────────────────────────────────────────────
# 6.1 accounts
# ─────────────────────────────────────────────────────────────────────────────
class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # platform account ID
    username: Mapped[str] = mapped_column(String, nullable=False)
    acct: Mapped[str | None] = mapped_column(String)
    display_name: Mapped[str | None] = mapped_column(String)
    url: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime | None] = mapped_column(_TS)
    first_seen_at: Mapped[datetime] = mapped_column(_TS, nullable=False, default=utcnow)
    last_checked_at: Mapped[datetime | None] = mapped_column(_TS)
    is_active_target: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONType)

    snapshots: Mapped[list[AccountSnapshot]] = relationship(
        back_populates="account", cascade="all, delete-orphan"
    )
    statuses: Mapped[list[Status]] = relationship(back_populates="account")

    __table_args__ = (Index("ix_accounts_active", "is_active_target"),)


# ─────────────────────────────────────────────────────────────────────────────
# 6.2 account_snapshots  (time-series of mutable profile fields)
# ─────────────────────────────────────────────────────────────────────────────
class AccountSnapshot(Base):
    __tablename__ = "account_snapshots"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(_TS, nullable=False, default=utcnow)
    display_name: Mapped[str | None] = mapped_column(String)
    note_html: Mapped[str | None] = mapped_column(Text)
    followers_count: Mapped[int | None] = mapped_column(BigInteger)
    following_count: Mapped[int | None] = mapped_column(BigInteger)
    statuses_count: Mapped[int | None] = mapped_column(BigInteger)
    avatar_url: Mapped[str | None] = mapped_column(String)
    header_url: Mapped[str | None] = mapped_column(String)
    content_hash: Mapped[str | None] = mapped_column(String)

    account: Mapped[Account] = relationship(back_populates="snapshots")

    __table_args__ = (Index("ix_snap_account_time", "account_id", "captured_at"),)


# ─────────────────────────────────────────────────────────────────────────────
# 6.3 statuses  (posts, replies, and reblog wrappers — one entity type)
# ─────────────────────────────────────────────────────────────────────────────
class Status(Base):
    __tablename__ = "statuses"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # platform status ID
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(_TS, nullable=False)
    edited_at: Mapped[datetime | None] = mapped_column(_TS)
    url: Mapped[str | None] = mapped_column(String)
    uri: Mapped[str | None] = mapped_column(String)
    # Soft references (indexed, NOT foreign keys): the referenced status may be
    # outside the archive — a reply to an untracked account, or a boost of a
    # since-deleted original. Enforcing these as FKs would force unbounded
    # ancestor fetching or reject legitimate rows. Author (account_id) stays a
    # hard FK because the author is always known.
    in_reply_to_id: Mapped[str | None] = mapped_column(String)
    in_reply_to_account_id: Mapped[str | None] = mapped_column(String)
    reblog_of_id: Mapped[str | None] = mapped_column(String)
    is_reblog: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    visibility: Mapped[str | None] = mapped_column(String)
    sensitive: Mapped[bool | None] = mapped_column(Boolean)
    spoiler_text: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String)
    content_html: Mapped[str | None] = mapped_column(Text)
    content_text: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    # Which feed this status came from (multi-source archive): "federal_register",
    # "presidential_documents", "whitehouse", or "news". Every adapter sets this
    # explicitly on insert and it is never updated; the default only catches a
    # writer that forgot to.
    source: Mapped[str] = mapped_column(String, nullable=False, default="unknown")
    # Human-facing type/label used as the badge and for faceting/filtering, e.g.
    # "Proclamation", "Remarks", "Releases", or a news publisher ("CNN").
    kind: Mapped[str | None] = mapped_column(String)
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deleted_detected_at: Mapped[datetime | None] = mapped_column(_TS)
    first_seen_at: Mapped[datetime] = mapped_column(_TS, nullable=False, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(_TS, nullable=False, default=utcnow)
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONType)

    account: Mapped[Account] = relationship(back_populates="statuses")
    versions: Mapped[list[StatusVersion]] = relationship(
        back_populates="status", cascade="all, delete-orphan"
    )
    metrics: Mapped[list[StatusMetric]] = relationship(
        back_populates="status", cascade="all, delete-orphan"
    )
    media: Mapped[list[Media]] = relationship(
        back_populates="status", cascade="all, delete-orphan"
    )
    sentiment: Mapped[StatusSentiment | None] = relationship(
        back_populates="status", cascade="all, delete-orphan", uselist=False
    )
    summary: Mapped[StatusSummary | None] = relationship(
        back_populates="status", cascade="all, delete-orphan", uselist=False
    )
    stock_mentions: Mapped[list[StockMention]] = relationship(
        back_populates="status", cascade="all, delete-orphan"
    )
    topics: Mapped[list[StatusTopic]] = relationship(
        back_populates="status", cascade="all, delete-orphan"
    )
    entities: Mapped[list[StatusEntity]] = relationship(
        back_populates="status", cascade="all, delete-orphan"
    )
    impact: Mapped[StatusImpact | None] = relationship(
        back_populates="status", cascade="all, delete-orphan", uselist=False
    )
    sectors: Mapped[list[StatusSector]] = relationship(
        back_populates="status", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_status_account_created", "account_id", "created_at"),
        Index("ix_status_reply", "in_reply_to_id"),
        Index("ix_status_reblog", "reblog_of_id"),
        Index("ix_status_deleted", "is_deleted"),
        Index("ix_status_source", "source"),
        Index("ix_status_kind", "kind"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 6.4 status_versions  (immutable edit history)
# ─────────────────────────────────────────────────────────────────────────────
class StatusVersion(Base):
    __tablename__ = "status_versions"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    status_id: Mapped[str] = mapped_column(ForeignKey("statuses.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(_TS, nullable=False, default=utcnow)
    edited_at: Mapped[datetime | None] = mapped_column(_TS)
    content_html: Mapped[str | None] = mapped_column(Text)
    content_text: Mapped[str | None] = mapped_column(Text)
    spoiler_text: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONType)

    status: Mapped[Status] = relationship(back_populates="versions")

    __table_args__ = (
        UniqueConstraint("status_id", "version", name="uq_status_versions_status_version"),
        Index("ix_ver_status", "status_id", "version"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 6.5 status_metrics  (time-series of volatile counts)
# ─────────────────────────────────────────────────────────────────────────────
class StatusMetric(Base):
    __tablename__ = "status_metrics"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    status_id: Mapped[str] = mapped_column(ForeignKey("statuses.id"), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(_TS, nullable=False, default=utcnow)
    replies_count: Mapped[int | None] = mapped_column(BigInteger)
    reblogs_count: Mapped[int | None] = mapped_column(BigInteger)
    favourites_count: Mapped[int | None] = mapped_column(BigInteger)

    status: Mapped[Status] = relationship(back_populates="metrics")

    __table_args__ = (Index("ix_metrics_status_time", "status_id", "captured_at"),)


# ─────────────────────────────────────────────────────────────────────────────
# 6.5b status_sentiment  (derived enrichment, 1:1 with a status)
# ─────────────────────────────────────────────────────────────────────────────
class StatusSentiment(Base):
    """A FinBERT sentiment reading for one status.

    Derived data, kept out of ``statuses`` so the captured record stays exactly as
    ingested and a re-score never rewrites it. ``scored_content_hash`` records
    *which* text produced this reading, so an edited status can be detected as
    stale and re-scored without blindly redoing the whole archive.
    """

    __tablename__ = "status_sentiment"

    status_id: Mapped[str] = mapped_column(ForeignKey("statuses.id"), primary_key=True)
    model: Mapped[str] = mapped_column(String, nullable=False)
    # "positive" | "negative" | "neutral" — the argmax of the three probabilities.
    label: Mapped[str] = mapped_column(String, nullable=False)
    # Confidence of the winning label (max of the three), in [0, 1].
    score: Mapped[float] = mapped_column(Double, nullable=False)
    positive: Mapped[float] = mapped_column(Double, nullable=False)
    negative: Mapped[float] = mapped_column(Double, nullable=False)
    neutral: Mapped[float] = mapped_column(Double, nullable=False)
    # positive − negative, in [-1, 1]: one signed number to sort/aggregate on.
    compound: Mapped[float] = mapped_column(Double, nullable=False)
    scored_content_hash: Mapped[str | None] = mapped_column(String)
    scored_at: Mapped[datetime] = mapped_column(_TS, nullable=False, default=utcnow)

    status: Mapped[Status] = relationship(back_populates="sentiment")

    __table_args__ = (
        Index("ix_sentiment_label", "label"),
        Index("ix_sentiment_compound", "compound"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 6.5c status_summary  (derived enrichment, 1:1 with a status)
# ─────────────────────────────────────────────────────────────────────────────
class StatusSummary(Base):
    """A machine-generated condensation of a status's text.

    Kept strictly separate from the publisher's own summary, which lives in
    ``statuses.content_text`` as captured. A model paraphrase of political
    reporting is an interpretation, not a record, so the two must never be
    conflated — the UI labels this one as generated.
    """

    __tablename__ = "status_summary"

    status_id: Mapped[str] = mapped_column(ForeignKey("statuses.id"), primary_key=True)
    model: Mapped[str] = mapped_column(String, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    # Hash of the text that was condensed, so an edited article is re-summarized.
    source_content_hash: Mapped[str | None] = mapped_column(String)
    generated_at: Mapped[datetime] = mapped_column(_TS, nullable=False, default=utcnow)

    status: Mapped[Status] = relationship(back_populates="summary")


# ─────────────────────────────────────────────────────────────────────────────
# 6.5d stock_mentions  (derived: a company named in a status)
# ─────────────────────────────────────────────────────────────────────────────
class StockMention(Base):
    """A publicly-traded company named in a status.

    Derived by the detection pass from a curated ticker dictionary, so — like
    sentiment and summaries — it never touches the captured text and is fully
    re-derivable. The set of distinct tickers here IS the Trump watchlist that
    drives the market refresh and the Upcoming Reports tab.
    """

    __tablename__ = "stock_mentions"

    status_id: Mapped[str] = mapped_column(ForeignKey("statuses.id"), primary_key=True)
    ticker: Mapped[str] = mapped_column(String, primary_key=True)
    # The exact alias that matched ("Truth Social"), kept for display and audit.
    alias: Mapped[str | None] = mapped_column(String)
    first_seen_at: Mapped[datetime] = mapped_column(_TS, nullable=False, default=utcnow)

    status: Mapped[Status] = relationship(back_populates="stock_mentions")

    __table_args__ = (Index("ix_stock_mentions_ticker", "ticker"),)


# ─────────────────────────────────────────────────────────────────────────────
# 6.5e company_market  (cache of live quote + next earnings, keyed by ticker)
# ─────────────────────────────────────────────────────────────────────────────
class CompanyMarket(Base):
    """Cached market data for a watchlist company (refreshed from Nasdaq).

    Not derived from the archive — this is external, time-sensitive data fetched
    on demand and cached so the dashboard never blocks on the network. One row per
    ticker; ``refreshed_at`` says how stale the quote is.
    """

    __tablename__ = "company_market"

    ticker: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str | None] = mapped_column(String)
    # Live quote (strings kept as fetched, e.g. "$320.95", "-0.22%").
    last_price: Mapped[str | None] = mapped_column(String)
    net_change: Mapped[str | None] = mapped_column(String)
    pct_change: Mapped[str | None] = mapped_column(String)
    delta_indicator: Mapped[str | None] = mapped_column(String)  # "up" | "down"
    market_cap: Mapped[str | None] = mapped_column(String)
    price_as_of: Mapped[str | None] = mapped_column(String)
    # Next scheduled quarterly report.
    next_earnings_date: Mapped[str | None] = mapped_column(String)  # ISO date
    next_earnings_eps_forecast: Mapped[str | None] = mapped_column(String)
    next_earnings_time: Mapped[str | None] = mapped_column(String)  # pre/after market
    quote_error: Mapped[str | None] = mapped_column(String)  # last fetch problem, if any
    refreshed_at: Mapped[datetime] = mapped_column(_TS, nullable=False, default=utcnow)

    __table_args__ = (Index("ix_company_market_earnings", "next_earnings_date"),)


# ─────────────────────────────────────────────────────────────────────────────
# 6.6 media  +  6.7 media_blobs
# ─────────────────────────────────────────────────────────────────────────────
class MediaBlob(Base):
    __tablename__ = "media_blobs"

    sha256: Mapped[str] = mapped_column(String, primary_key=True)
    byte_size: Mapped[int | None] = mapped_column(BigInteger)
    mime_type: Mapped[str | None] = mapped_column(String)
    storage_path: Mapped[str | None] = mapped_column(String)
    downloaded_at: Mapped[datetime | None] = mapped_column(_TS)

    media: Mapped[list[Media]] = relationship(back_populates="blob")


class Media(Base):
    __tablename__ = "media"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # platform media ID
    status_id: Mapped[str] = mapped_column(ForeignKey("statuses.id"), nullable=False)
    type: Mapped[str | None] = mapped_column(String)
    url: Mapped[str | None] = mapped_column(String)
    preview_url: Mapped[str | None] = mapped_column(String)
    remote_url: Mapped[str | None] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(Text)
    blurhash: Mapped[str | None] = mapped_column(String)
    meta: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    blob_sha256: Mapped[str | None] = mapped_column(ForeignKey("media_blobs.sha256"))
    first_seen_at: Mapped[datetime] = mapped_column(_TS, nullable=False, default=utcnow)

    status: Mapped[Status] = relationship(back_populates="media")
    blob: Mapped[MediaBlob | None] = relationship(back_populates="media")

    __table_args__ = (
        Index("ix_media_status", "status_id"),
        Index("ix_media_blob", "blob_sha256"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 6.8 mentions
# ─────────────────────────────────────────────────────────────────────────────
class Mention(Base):
    __tablename__ = "mentions"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    status_id: Mapped[str] = mapped_column(ForeignKey("statuses.id"), nullable=False)
    mentioned_account_id: Mapped[str | None] = mapped_column(String)
    username: Mapped[str | None] = mapped_column(String)
    acct: Mapped[str | None] = mapped_column(String)
    url: Mapped[str | None] = mapped_column(String)

    __table_args__ = (
        UniqueConstraint(
            "status_id", "mentioned_account_id", name="uq_mentions_status_mentioned_account_id"
        ),
        Index("ix_mentions_acct", "mentioned_account_id"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 6.9 hashtags  +  status_hashtags  (many-to-many)
# ─────────────────────────────────────────────────────────────────────────────
class Hashtag(Base):
    __tablename__ = "hashtags"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)  # lowercased
    first_seen_at: Mapped[datetime] = mapped_column(_TS, nullable=False, default=utcnow)

    __table_args__ = (UniqueConstraint("name", name="uq_hashtags_name"),)


class StatusHashtag(Base):
    __tablename__ = "status_hashtags"

    status_id: Mapped[str] = mapped_column(ForeignKey("statuses.id"), primary_key=True)
    hashtag_id: Mapped[int] = mapped_column(ForeignKey("hashtags.id"), primary_key=True)

    __table_args__ = (Index("ix_sh_tag", "hashtag_id"),)


# ─────────────────────────────────────────────────────────────────────────────
# 6.10 urls  (link cards / extracted links)
# ─────────────────────────────────────────────────────────────────────────────
class Url(Base):
    __tablename__ = "urls"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    status_id: Mapped[str] = mapped_column(ForeignKey("statuses.id"), nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    provider_name: Mapped[str | None] = mapped_column(String)
    image_url: Mapped[str | None] = mapped_column(String)

    __table_args__ = (
        Index("ix_urls_status", "status_id"),
        Index("ix_urls_url", "url"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 6.11 scrape_jobs  +  6.12 failures
# ─────────────────────────────────────────────────────────────────────────────
class ScrapeJob(Base):
    __tablename__ = "scrape_jobs"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    job_type: Mapped[str] = mapped_column(String, nullable=False)
    target_account_id: Mapped[str | None] = mapped_column(ForeignKey("accounts.id"))
    params: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    status: Mapped[str] = mapped_column(String, nullable=False, default="queued")
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    scheduled_at: Mapped[datetime | None] = mapped_column(_TS)
    started_at: Mapped[datetime | None] = mapped_column(_TS)
    finished_at: Mapped[datetime | None] = mapped_column(_TS)
    next_retry_at: Mapped[datetime | None] = mapped_column(_TS)
    error_id: Mapped[int | None] = mapped_column(BigInteger)

    __table_args__ = (
        Index("ix_jobs_status_retry", "status", "next_retry_at"),
        Index("ix_jobs_type", "job_type"),
    )


class Failure(Base):
    __tablename__ = "failures"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("scrape_jobs.id"))
    occurred_at: Mapped[datetime] = mapped_column(_TS, nullable=False, default=utcnow)
    category: Mapped[str | None] = mapped_column(String)
    http_status: Mapped[int | None] = mapped_column(Integer)
    message: Mapped[str | None] = mapped_column(Text)
    response_excerpt: Mapped[str | None] = mapped_column(Text)
    traceback_hash: Mapped[str | None] = mapped_column(String)
    raw_context: Mapped[dict[str, Any] | None] = mapped_column(JSONType)

    __table_args__ = (
        Index("ix_fail_category_time", "category", "occurred_at"),
        Index("ix_fail_tb", "traceback_hash"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 6.13 checkpoint_state  (durable resume cursors)
# ─────────────────────────────────────────────────────────────────────────────
class CheckpointState(Base):
    __tablename__ = "checkpoint_state"

    target_account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), primary_key=True)
    phase: Mapped[str] = mapped_column(String, nullable=False, default="bootstrap")
    backfill_cursor: Mapped[str | None] = mapped_column(String)
    frontier_cursor: Mapped[str | None] = mapped_column(String)
    backfill_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_resync_at: Mapped[datetime | None] = mapped_column(_TS)
    updated_at: Mapped[datetime] = mapped_column(_TS, nullable=False, default=utcnow)


# ─────────────────────────────────────────────────────────────────────────────
# 6.14 raw_payloads  (append-only capture; re-derivation source of truth)
# ─────────────────────────────────────────────────────────────────────────────
class RawPayload(Base):
    __tablename__ = "raw_payloads"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    fetched_at: Mapped[datetime] = mapped_column(_TS, nullable=False, default=utcnow)
    endpoint: Mapped[str | None] = mapped_column(String)
    request_params: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    http_status: Mapped[int | None] = mapped_column(Integer)
    entity_type: Mapped[str | None] = mapped_column(String)
    entity_id: Mapped[str | None] = mapped_column(String)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    payload_sha256: Mapped[str | None] = mapped_column(String)

    __table_args__ = (
        Index("ix_raw_entity", "entity_type", "entity_id"),
        Index("ix_raw_time", "fetched_at"),
        UniqueConstraint("payload_sha256", name="uq_raw_payloads_payload_sha256"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 6.15 crawler_metrics  (operational time-series; long-retention copy)
# ─────────────────────────────────────────────────────────────────────────────
class CrawlerMetric(Base):
    __tablename__ = "crawler_metrics"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    captured_at: Mapped[datetime] = mapped_column(_TS, nullable=False, default=utcnow)
    metric: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[float | None] = mapped_column(Double)
    labels: Mapped[dict[str, Any] | None] = mapped_column(JSONType)

    __table_args__ = (Index("ix_cmetrics", "metric", "captured_at"),)


# ─────────────────────────────────────────────────────────────────────────────
# 6.16 status_topics  (derived: curated topic hits)
# ─────────────────────────────────────────────────────────────────────────────
class StatusTopic(Base):
    """A curated topic matched in a status.

    Derived, like sentiment and stock mentions: never touches the captured text,
    fully re-derivable, safe to drop and rebuild. One row per (status, topic)
    however many of the topic's terms appeared.
    """

    __tablename__ = "status_topics"

    status_id: Mapped[str] = mapped_column(ForeignKey("statuses.id"), primary_key=True)
    topic: Mapped[str] = mapped_column(String, primary_key=True)
    # The exact term that matched ("section 232"), kept for display and for
    # auditing whichever term turns out to be the noisy one.
    matched_term: Mapped[str | None] = mapped_column(String)
    detected_at: Mapped[datetime] = mapped_column(_TS, nullable=False, default=utcnow)

    status: Mapped[Status] = relationship(back_populates="topics")

    __table_args__ = (Index("ix_status_topics_topic", "topic"),)


# ─────────────────────────────────────────────────────────────────────────────
# 6.17 status_entities  (derived: countries, blocs, agencies)
# ─────────────────────────────────────────────────────────────────────────────
class StatusEntity(Base):
    """A country, bloc, or agency named in a status.

    Companies deliberately live in ``stock_mentions`` instead — they already had
    a curated matcher and a market cache hanging off them.
    """

    __tablename__ = "status_entities"

    status_id: Mapped[str] = mapped_column(ForeignKey("statuses.id"), primary_key=True)
    entity_key: Mapped[str] = mapped_column(String, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String, nullable=False)  # country|bloc|agency
    alias: Mapped[str | None] = mapped_column(String)
    detected_at: Mapped[datetime] = mapped_column(_TS, nullable=False, default=utcnow)

    status: Mapped[Status] = relationship(back_populates="entities")

    __table_args__ = (
        Index("ix_status_entities_key", "entity_key"),
        Index("ix_status_entities_type", "entity_type"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 6.18 status_impact  (derived: the ranking score and its components)
# ─────────────────────────────────────────────────────────────────────────────
class StatusImpact(Base):
    """Impact ranking for a status, with every component kept alongside the total.

    The components are the point. A bare score cannot be explained to a reader or
    corrected by an operator; with authority/topic/actionability/corroboration/
    market sensitivity on the row, the dashboard can say *why* an item ranks
    where it does, and re-weighting is an UPDATE rather than a re-run of every
    model pass.

    ``corroboration`` and ``market_sensitivity`` are nullable on purpose: NULL
    means "not measured yet" (the clustering and market passes are separate) and
    is excluded from the weighted average, where 0.0 would mean "measured, and
    there is no support" and would drag every row down to routine.
    """

    __tablename__ = "status_impact"

    status_id: Mapped[str] = mapped_column(ForeignKey("statuses.id"), primary_key=True)

    authority: Mapped[float] = mapped_column(Double, nullable=False)
    # Human-readable reason for the authority score ("Executive Order").
    authority_label: Mapped[str | None] = mapped_column(String)
    topic: Mapped[float] = mapped_column(Double, nullable=False)
    actionability: Mapped[float] = mapped_column(Double, nullable=False)
    corroboration: Mapped[float | None] = mapped_column(Double)
    market_sensitivity: Mapped[float | None] = mapped_column(Double)

    impact_score: Mapped[float] = mapped_column(Double, nullable=False)
    tier: Mapped[str] = mapped_column(String, nullable=False)

    # Which weight set produced this score, so a re-weight is detectable.
    # Market direction for the sector named — restrictive / supportive /
    # mentioned — kept beside the score because it is what a reader acts on.
    stance: Mapped[str | None] = mapped_column(String)
    stance_confidence: Mapped[float | None] = mapped_column(Double)

    weights_version: Mapped[str] = mapped_column(String, nullable=False)
    # Lets a re-run skip rows whose text has not changed since scoring.
    scored_content_hash: Mapped[str | None] = mapped_column(String)
    scored_at: Mapped[datetime] = mapped_column(_TS, nullable=False, default=utcnow)

    status: Mapped[Status] = relationship(back_populates="impact")

    __table_args__ = (
        Index("ix_status_impact_score", "impact_score"),
        Index("ix_status_impact_tier", "tier"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 6.19 status_sectors  (derived: market sectors a status touches)
# ─────────────────────────────────────────────────────────────────────────────
class StatusSector(Base):
    """A market sector implicated by a status.

    Company detection needs a company named by name, which almost no policy item
    does; sectors are matched from policy vocabulary instead, so an item about
    steel tariffs resolves to Materials even though it names no producer.
    """

    __tablename__ = "status_sectors"

    status_id: Mapped[str] = mapped_column(ForeignKey("statuses.id"), primary_key=True)
    sector: Mapped[str] = mapped_column(String, primary_key=True)
    matched_term: Mapped[str | None] = mapped_column(String)
    detected_at: Mapped[datetime] = mapped_column(_TS, nullable=False, default=utcnow)

    status: Mapped[Status] = relationship(back_populates="sectors")

    __table_args__ = (Index("ix_status_sectors_sector", "sector"),)


# ─────────────────────────────────────────────────────────────────────────────
# 6.20 status_analysis  (derived: AI-written breakdown, generated on demand)
# ─────────────────────────────────────────────────────────────────────────────
class StatusAnalysis(Base):
    """A structured breakdown of one story, written by a language model.

    Generated the first time a reader asks for it and stored, so each story costs
    at most one generation. Kept apart from the captured record and labelled as
    machine-written wherever it is shown.
    """

    __tablename__ = "status_analysis"

    status_id: Mapped[str] = mapped_column(ForeignKey("statuses.id"), primary_key=True)
    model: Mapped[str] = mapped_column(String, nullable=False)
    # full_text / partial / headline_only — whether the article was actually read.
    source_quality: Mapped[str] = mapped_column(String, nullable=False)
    analysis: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    generated_at: Mapped[datetime] = mapped_column(_TS, nullable=False, default=utcnow)

    __table_args__ = (Index("ix_status_analysis_generated", "generated_at"),)
