"""FastAPI application: a read-only dashboard + JSON API over the archive.

Endpoints:
    GET /               → the dashboard HTML
    GET /api/stats      → totals and per-source counts
    GET /api/statuses   → paginated, searchable, filterable archive items
"""

from __future__ import annotations

import socket
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select

from archiver.storage.db import Database
from archiver.storage.models import Status
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
        return {
            "total": sum(row[1] for row in src),
            "sources": [{"key": row[0], "count": row[1]} for row in src],
            "kinds": [{"key": row[0], "count": row[1]} for row in knd],
        }

    @app.get("/api/statuses")
    async def statuses(
        q: str | None = None,
        source: str | None = None,
        kind: str | None = None,
        since: str | None = None,
        until: str | None = None,
        limit: int = Query(25, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        stmt = select(Status).order_by(Status.created_at.desc())
        if source:
            stmt = stmt.where(Status.source == source)
        if kind:
            stmt = stmt.where(Status.kind == kind)
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
