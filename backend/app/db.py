"""Async engine and session dependency.

Providers hand out driver-less ``postgresql://`` URLs; the async engine needs
an explicit driver, so normalize here the same way the archiver does.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


def to_async_url(url: str) -> str:
    """Return ``url`` with a driver the async engine can use."""
    scheme, sep, rest = url.partition("://")
    if not sep:
        return url
    if scheme in ("postgres", "postgresql"):
        return "postgresql+psycopg://" + rest
    return url


def to_sync_url(url: str) -> str:
    """Return ``url`` with a blocking driver, for Celery tasks."""
    scheme, sep, rest = url.partition("://")
    if not sep:
        return url
    if scheme in ("postgres", "postgresql", "postgresql+asyncpg"):
        return "postgresql+psycopg://" + rest
    return url


_engine: AsyncEngine = create_async_engine(to_async_url(get_settings().database_url))
_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    _engine, expire_on_commit=False
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding one session per request."""
    async with _session_factory() as session:
        yield session


async def dispose_engine() -> None:
    """Close pooled connections on shutdown."""
    await _engine.dispose()


# Writes happen in Celery tasks, which are blocking; reads happen in the API,
# which is async. Each side gets the engine that suits it.
_sync_engine: Engine = create_engine(to_sync_url(get_settings().database_url), pool_pre_ping=True)
_sync_session_factory: sessionmaker[Session] = sessionmaker(_sync_engine, expire_on_commit=False)


@contextmanager
def sync_session() -> Iterator[Session]:
    """Blocking session for worker tasks. Commits on success, rolls back on error."""
    session = _sync_session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
