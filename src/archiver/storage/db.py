"""Async database engine, session factory, and lifecycle helpers.

Works with any SQLAlchemy async driver. Two profiles are exercised:
  * ``sqlite+aiosqlite`` — tests and the minimal single-account profile.
  * ``postgresql+psycopg`` (async) — production / scale profile.

SQLite does not enforce foreign keys unless ``PRAGMA foreign_keys=ON`` is set per
connection, so we install that automatically — otherwise FK-integrity guarantees
would silently not hold in tests.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from archiver.storage.models import Base


def _install_sqlite_fk_pragma(engine: AsyncEngine) -> None:
    if engine.sync_engine.dialect.name != "sqlite":
        return

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection: Any, _record: Any) -> None:  # noqa: ANN401
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


class Database:
    """Owns the async engine and hands out sessions."""

    def __init__(
        self,
        url: str,
        *,
        echo: bool = False,
        engine_kwargs: dict[str, Any] | None = None,
    ) -> None:
        self.url = url
        self.engine: AsyncEngine = create_async_engine(url, echo=echo, **(engine_kwargs or {}))
        _install_sqlite_fk_pragma(self.engine)
        self.dialect: str = self.engine.sync_engine.dialect.name
        self.session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self.engine, expire_on_commit=False
        )

    @classmethod
    def in_memory(cls, *, echo: bool = False) -> Database:
        """A shared in-memory SQLite DB (single connection) for tests."""
        from sqlalchemy.pool import StaticPool

        return cls(
            "sqlite+aiosqlite:///:memory:",
            echo=echo,
            engine_kwargs={
                "connect_args": {"check_same_thread": False},
                "poolclass": StaticPool,
            },
        )

    def session(self) -> AsyncSession:
        """Open a new session (use as an async context manager)."""
        return self.session_factory()

    async def create_all(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def drop_all(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    async def dispose(self) -> None:
        await self.engine.dispose()
