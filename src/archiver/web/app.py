"""FastAPI application: a read-only dashboard + JSON API over the archive.

Endpoints:
    GET /               → the dashboard HTML
    GET /api/stats      → totals and per-source counts
    GET /api/facets     → sources, kinds, sentiments, topics, impact tiers
    GET /api/statuses   → paginated, searchable, filterable archive items

Impact ranking is exposed through ``/api/statuses`` (``sort=impact`` plus the
``tier`` and ``topic`` filters) rather than a separate ``/api/impact`` endpoint:
a second route would have to duplicate the search, date-bound and pagination
logic, and the two would drift. One list endpoint, one set of filters.
"""

from __future__ import annotations

import re
import socket
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from archiver.analysis.signals import is_generic_label
from archiver.reference.sectors import SECTORS
from archiver.reference.tickers import TICKERS
from archiver.reference.topics import TOPICS
from archiver.storage.db import Database
from archiver.storage.models import (
    CompanyMarket,
    Status,
    StatusEntity,
    StatusImpact,
    StatusSector,
    StatusSentiment,
    StatusTopic,
    StockMention,
)
from archiver.web.page import INDEX_HTML


def _parse_bound(value: str | None, *, end: bool) -> datetime | None:
    """Parse an ISO date/datetime filter bound into naive-UTC (how rows are stored).

    A date-only ``end`` bound is advanced by a day so the whole day is included.
    """
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC)
    parsed = parsed.replace(tzinfo=None)
    if end and len(value) <= 10:  # date-only → include the full day
        parsed += timedelta(days=1)
    return parsed


def find_free_port(host: str, preferred: int, span: int = 20) -> int:
    """Return ``preferred`` if bindable, else the next free port within ``span``.

    Avoids the confusing situation where another process (e.g. an SSH tunnel on
    :8000) already holds the port and the browser shows the wrong app.
    """
    for candidate in range(preferred, preferred + span):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, candidate))
                return candidate
            except OSError:
                continue
    return preferred  # give up; let uvicorn surface the bind error


def _to_sentiment(reading: StatusSentiment | None) -> dict[str, Any] | None:
    """Shape a stored sentiment reading for the API (None when never scored)."""
    if reading is None:
        return None
    return {
        "label": reading.label,
        "score": round(reading.score, 4),
        "compound": round(reading.compound, 4),
        "positive": round(reading.positive, 4),
        "negative": round(reading.negative, 4),
        "neutral": round(reading.neutral, 4),
        "model": reading.model,
        "scored_at": reading.scored_at.isoformat() if reading.scored_at else None,
    }


# Separators an RSS description tends to leave behind once the restated
# headline in front of them is removed.
_LEADING_PUNCT = re.compile(r"^[\s\u2014\u2013:·|,;.-]+")
# Official sources prefix the stored text with the document type —
# "[Executive Order] Ending Certain Tariff Actions" — while the title field
# holds the bare title. Ignore that prefix when deciding whether the body is
# saying anything the headline has not.
_TYPE_PREFIX = re.compile(r"^\[[^\]]{1,40}\]\s*")


def _body(text: str, title: str) -> str:
    """The article body: whatever the headline does not already say.

    RSS descriptions very often *restate* the headline and then trail off, so an
    exact-match check is not enough — on this corpus about half of all items
    would otherwise render the same sentence twice in a row. When the body opens
    with the headline, that opening is stripped; when what remains is only a
    fragment, there is no body worth showing.
    """
    body = text.split("\n", 1)[1].strip() if "\n" in text else text.strip()
    head = title.strip()
    if not body or not head or body == head:
        return ""
    body = _TYPE_PREFIX.sub("", body).strip()
    if not body or body == head:
        return ""
    low_body, low_head = body.lower(), head.lower()
    # The overlap runs in both directions on this corpus. Google News titles are
    # the description plus a " - Publisher" suffix, so the *title* starts with
    # the body and the body adds nothing at all. Full article rows are the other
    # way round: the body opens by restating the headline and then continues.
    if low_head.startswith(low_body):
        return ""
    if low_body.startswith(low_head):
        body = _LEADING_PUNCT.sub("", body[len(head) :]).strip()
    # A handful of leftover words is noise, not a summary.
    return body if len(body) >= 40 else ""


def _to_impact(row: StatusImpact | None) -> dict[str, Any] | None:
    """Shape a stored impact score for the API (None when never classified).

    Components ship alongside the total so the UI can explain a ranking instead
    of asserting a number; ``reasons`` is that explanation pre-assembled, since
    every client would otherwise rebuild the same sentence.
    """
    if row is None:
        return None
    reasons: list[str] = []
    # "news coverage" under every news headline is noise; a real document type
    # ("Executive Order") is the single most useful thing on the card.
    if row.authority_label and not is_generic_label(row.authority_label):
        reasons.append(row.authority_label)
    if row.actionability >= 0.65:
        reasons.append("committed language")
    elif row.actionability <= 0.35:
        reasons.append("speculative language")
    if row.corroboration is not None:
        reasons.append(f"{int(round(row.corroboration * 10))} outlets")
    return {
        "score": round(row.impact_score, 4),
        "tier": row.tier,
        "stance": row.stance,
        "stance_confidence": row.stance_confidence,
        "authority": round(row.authority, 4),
        "authority_label": row.authority_label,
        "topic": round(row.topic, 4),
        "actionability": round(row.actionability, 4),
        "corroboration": (
            round(row.corroboration, 4) if row.corroboration is not None else None
        ),
        "market_sensitivity": (
            round(row.market_sensitivity, 4)
            if row.market_sensitivity is not None
            else None
        ),
        "reasons": reasons,
    }


def _to_topics(rows: list[StatusTopic]) -> list[dict[str, Any]]:
    """Topic hits with their display labels, heaviest first."""
    out = [
        {
            "key": r.topic,
            "label": TOPICS[r.topic].label if r.topic in TOPICS else r.topic,
            "weight": TOPICS[r.topic].weight if r.topic in TOPICS else 0.0,
            "matched_term": r.matched_term,
        }
        for r in rows
    ]
    return sorted(out, key=lambda t: t["weight"], reverse=True)


def _to_entities(rows: list[StatusEntity]) -> list[dict[str, Any]]:
    """Named countries, blocs and agencies, countries first (they carry most)."""
    order = {"country": 0, "bloc": 1, "agency": 2}
    out = [
        {"key": r.entity_key, "type": r.entity_type, "alias": r.alias} for r in rows
    ]
    return sorted(out, key=lambda e: (order.get(e["type"], 9), e["key"]))


def _to_sectors(rows: list[StatusSector]) -> list[dict[str, Any]]:
    """Market sectors an item touches, each with a tradable proxy.

    The ETF is what makes a sector an *answer* rather than a label: an item about
    steel tariffs names no company, but "Materials — XLB" is something a reader
    can act on.
    """
    out = []
    for r in rows:
        sec = SECTORS.get(r.sector)
        out.append(
            {
                "key": r.sector,
                "label": sec.label if sec else r.sector,
                "etf": sec.etf if sec else None,
                "tickers": list(sec.tickers) if sec else [],
                "matched_term": r.matched_term,
            }
        )
    return sorted(out, key=lambda x: x["label"])


def _to_stocks(rows: list[StockMention]) -> list[dict[str, Any]]:
    """Companies named in a status, with the alias that actually matched.

    The alias is kept visible so a false positive is obvious at a glance —
    "mentioned as 'Truth Social'" is auditable in a way a bare ticker is not.
    """
    out = [
        {
            "ticker": r.ticker,
            "name": TICKERS[r.ticker].name if r.ticker in TICKERS else r.ticker,
            "alias": r.alias,
        }
        for r in rows
    ]
    return sorted(out, key=lambda c: c["ticker"])


def _to_item(status: Status) -> dict[str, Any]:
    raw = status.raw or {}
    text = status.content_text or ""
    title = raw.get("title") or (text.split("\n", 1)[0] if text else status.id)
    kind = (
        status.kind
        or raw.get("subtype")
        or raw.get("type")
        or raw.get("category")
        or status.source
    )
    return {
        "id": status.id,
        "created_at": status.created_at.isoformat() if status.created_at else None,
        "source": status.source,
        "kind": kind,
        "publisher": raw.get("publisher"),
        "title": title,
        "url": status.url,
        "text": text,
        # The publisher's own words, as captured.
        "summary": _body(text, str(title)),
        # A machine paraphrase — kept in a separate field so the UI can never
        # present generated text as if the publisher wrote it.
        "generated_summary": (
            {
                "text": status.summary.summary,
                "model": status.summary.model,
                "generated_at": (
                    status.summary.generated_at.isoformat()
                    if status.summary.generated_at
                    else None
                ),
            }
            if status.summary
            else None
        ),
        "sentiment": _to_sentiment(status.sentiment),
        "impact": _to_impact(status.impact),
        "topics": _to_topics(list(status.topics)),
        "entities": _to_entities(list(status.entities)),
        "stocks": _to_stocks(list(status.stock_mentions)),
        "sectors": _to_sectors(list(status.sectors)),
    }


def create_app(db: Database) -> FastAPI:
    app = FastAPI(title="Trump News Archive", docs_url="/api/docs")

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return INDEX_HTML

    @app.get("/api/stats")
    async def stats() -> dict[str, Any]:
        async with db.session() as session:
            total = await session.scalar(select(func.count()).select_from(Status))
            rows = (
                await session.execute(select(Status.source, func.count()).group_by(Status.source))
            ).all()
        by_source = {row[0]: row[1] for row in rows}
        return {"total": total or 0, "by_source": by_source}

    @app.get("/api/facets")
    async def facets() -> dict[str, Any]:
        async with db.session() as session:
            src = (
                await session.execute(
                    select(Status.source, func.count())
                    .group_by(Status.source)
                    .order_by(func.count().desc())
                )
            ).all()
            knd = (
                await session.execute(
                    select(Status.kind, func.count())
                    .where(Status.kind.is_not(None))
                    .group_by(Status.kind)
                    .order_by(func.count().desc())
                    .limit(14)
                )
            ).all()
            snt = (
                await session.execute(
                    select(StatusSentiment.label, func.count(), func.avg(StatusSentiment.compound))
                    .group_by(StatusSentiment.label)
                    .order_by(func.count().desc())
                )
            ).all()
            tpc = (
                await session.execute(
                    select(StatusTopic.topic, func.count())
                    .group_by(StatusTopic.topic)
                    .order_by(func.count().desc())
                )
            ).all()
            tir = (
                await session.execute(
                    select(StatusImpact.tier, func.count()).group_by(StatusImpact.tier)
                )
            ).all()
            sec = (
                await session.execute(
                    select(StatusSector.sector, func.count())
                    .group_by(StatusSector.sector)
                    .order_by(func.count().desc())
                )
            ).all()
            stn = (
                await session.execute(
                    select(StatusImpact.stance, func.count())
                    .where(StatusImpact.stance.is_not(None))
                    .group_by(StatusImpact.stance)
                )
            ).all()
            cmp = (
                await session.execute(
                    select(StockMention.ticker, func.count())
                    .group_by(StockMention.ticker)
                    .order_by(func.count().desc())
                )
            ).all()
            mkt = (
                await session.execute(
                    select(
                        CompanyMarket.ticker,
                        CompanyMarket.last_price,
                        CompanyMarket.pct_change,
                        CompanyMarket.delta_indicator,
                    )
                )
            ).all()
        quotes = {
            r[0]: {"last_price": r[1], "pct_change": r[2], "delta": r[3]} for r in mkt
        }
        # Tiers are a severity ladder, so present them in severity order rather
        # than by count — "critical" belongs at the top even when it is rarest.
        tier_rank = {"critical": 0, "high": 1, "notable": 2, "routine": 3}
        tiers = sorted(
            ({"key": row[0], "count": row[1]} for row in tir),
            key=lambda t: tier_rank.get(t["key"], 9),
        )
        return {
            "total": sum(row[1] for row in src),
            "sources": [{"key": row[0], "count": row[1]} for row in src],
            "sectors": [
                {
                    "key": row[0],
                    "label": SECTORS[row[0]].label if row[0] in SECTORS else row[0],
                    "etf": SECTORS[row[0]].etf if row[0] in SECTORS else None,
                    "count": row[1],
                }
                for row in sec
            ],
            "stances": [{"key": r[0], "count": r[1]} for r in stn],
            "companies": [
                {
                    "key": row[0],
                    "label": TICKERS[row[0]].name if row[0] in TICKERS else row[0],
                    "count": row[1],
                    "quote": quotes.get(row[0]),
                }
                for row in cmp
            ],
            "topics": [
                {
                    "key": row[0],
                    "label": TOPICS[row[0]].label if row[0] in TOPICS else row[0],
                    "count": row[1],
                }
                for row in tpc
            ],
            "tiers": tiers,
            "kinds": [{"key": row[0], "count": row[1]} for row in knd],
            "sentiments": [
                {"key": row[0], "count": row[1], "avg_compound": round(row[2] or 0.0, 4)}
                for row in snt
            ],
        }

    @app.get("/api/statuses")
    async def statuses(
        q: str | None = None,
        source: str | None = None,
        kind: str | None = None,
        sentiment: str | None = None,
        topic: str | None = None,
        tier: str | None = None,
        ticker: str | None = None,
        sector: str | None = None,
        stance: str | None = None,
        sort: str = Query("recent", pattern="^(recent|impact)$"),
        since: str | None = None,
        until: str | None = None,
        limit: int = Query(25, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        # selectinload keeps this one extra query per relationship instead of
        # N+1 per card.
        stmt = select(Status).options(
            selectinload(Status.sentiment),
            selectinload(Status.summary),
            selectinload(Status.impact),
            selectinload(Status.topics),
            selectinload(Status.entities),
            selectinload(Status.stock_mentions),
            selectinload(Status.sectors),
        )
        if sort == "impact":
            # Ties are common — three components over short headlines land on a
            # handful of values — so recency breaks them and the order stays
            # stable across requests instead of shuffling under pagination.
            stmt = stmt.join(StatusImpact).order_by(
                StatusImpact.impact_score.desc(), Status.created_at.desc()
            )
        else:
            stmt = stmt.order_by(Status.created_at.desc())
        if source:
            stmt = stmt.where(Status.source == source)
        if kind:
            stmt = stmt.where(Status.kind == kind)
        if sentiment:
            stmt = stmt.join(StatusSentiment).where(StatusSentiment.label == sentiment)
        if topic:
            stmt = stmt.where(
                Status.id.in_(
                    select(StatusTopic.status_id).where(StatusTopic.topic == topic)
                )
            )
        if sector:
            stmt = stmt.where(
                Status.id.in_(
                    select(StatusSector.status_id).where(StatusSector.sector == sector)
                )
            )
        if stance:
            stmt = stmt.where(
                Status.id.in_(
                    select(StatusImpact.status_id).where(StatusImpact.stance == stance)
                )
            )
        if ticker:
            stmt = stmt.where(
                Status.id.in_(
                    select(StockMention.status_id).where(StockMention.ticker == ticker)
                )
            )
        if tier:
            # An explicit tier filter can coexist with sort=impact, which already
            # joins the table — use a subquery so the join is never duplicated.
            stmt = stmt.where(
                Status.id.in_(
                    select(StatusImpact.status_id).where(StatusImpact.tier == tier)
                )
            )
        if q:
            stmt = stmt.where(Status.content_text.ilike(f"%{q}%"))
        since_dt = _parse_bound(since, end=False)
        until_dt = _parse_bound(until, end=True)
        if since_dt is not None:
            stmt = stmt.where(Status.created_at >= since_dt)
        if until_dt is not None:
            stmt = stmt.where(Status.created_at < until_dt)
        stmt = stmt.limit(limit).offset(offset)
        async with db.session() as session:
            rows = (await session.scalars(stmt)).all()
            items = [_to_item(row) for row in rows]
        return {"items": items, "count": len(items), "offset": offset, "limit": limit}

    return app
