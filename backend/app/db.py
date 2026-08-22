"""Async engine and session dependency.

Providers hand out driver-less ``postgresql://`` URLs; the async engine needs
an explicit driver, so normalize here the same way the archiver does.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings


def to_async_url(url: str) -> str:
    """Return ``url`` with a driver the async engine can use."""
    scheme, sep, rest = url.partition("://")
    if not sep:
        return url
    if scheme in ("postgres", "postgresql"):
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
