"""Database URL normalization.

Managed Postgres providers (Neon, Supabase, Render, …) hand out plain
``postgresql://`` — or, historically, ``postgres://`` — URLs with no driver in
the scheme. SQLAlchemy requires one, and the app and Alembic need *different*
engines from the same string: the app is async, migrations are sync.

Everything funnels through here so one ``DATABASE_URL`` secret works unchanged
for the web app, the CLI, and migrations. psycopg 3 backs both directions, so
Postgres normalizes to the same scheme either way; only SQLite differs.
"""

from __future__ import annotations

_PG_ASYNC = "postgresql+psycopg://"
_PG_SYNC = "postgresql+psycopg://"


def _strip_scheme(url: str) -> tuple[str, str]:
    scheme, sep, rest = url.partition("://")
    return (scheme, rest) if sep else ("", url)


def to_async_url(url: str) -> str:
    """Return ``url`` with a driver the async engine can use.

    Already-qualified URLs pass through untouched, so an operator who pins
    ``+asyncpg`` keeps it.
    """
    scheme, rest = _strip_scheme(url)
    if not rest:
        return url
    if scheme in ("postgres", "postgresql"):
        return _PG_ASYNC + rest
    if scheme == "sqlite":
        return "sqlite+aiosqlite://" + rest
    return url


def to_sync_url(url: str) -> str:
    """Return ``url`` with a driver Alembic's sync engine can use."""
    scheme, rest = _strip_scheme(url)
    if not rest:
        return url
    if scheme in ("postgres", "postgresql", "postgresql+asyncpg"):
        return _PG_SYNC + rest
    if scheme == "sqlite+aiosqlite":
        return "sqlite://" + rest
    return url
