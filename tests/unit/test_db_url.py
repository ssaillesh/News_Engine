"""Driver normalization for provider-issued database URLs.

Managed Postgres (Neon, Supabase, …) hands out driver-less URLs. One
``DATABASE_URL`` has to drive three consumers — the async app, the async
serverless handler, and Alembic's sync engine — so these pin the rewrites.
"""

from __future__ import annotations

import pytest

from archiver.storage.url import to_async_url, to_sync_url

NEON = "postgresql://user:pw@ep-x.us-east-2.aws.neon.tech/archive?sslmode=require"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # The case that matters: a bare provider URL must gain an async driver.
        (NEON, "postgresql+psycopg://user:pw@ep-x.us-east-2.aws.neon.tech/archive?sslmode=require"),
        ("postgres://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
        ("sqlite:///./archive.db", "sqlite+aiosqlite:///./archive.db"),
        # Already-qualified URLs pass through, so an explicit pin is honored.
        ("postgresql+asyncpg://u:p@h/db", "postgresql+asyncpg://u:p@h/db"),
        ("sqlite+aiosqlite:///./archive.db", "sqlite+aiosqlite:///./archive.db"),
    ],
)
def test_to_async_url(raw: str, expected: str) -> None:
    assert to_async_url(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (NEON, "postgresql+psycopg://user:pw@ep-x.us-east-2.aws.neon.tech/archive?sslmode=require"),
        ("postgres://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
        # Alembic is sync, so the async drivers must be swapped out, not kept.
        ("postgresql+asyncpg://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
        ("sqlite+aiosqlite:///./archive.db", "sqlite:///./archive.db"),
        ("sqlite:///./archive.db", "sqlite:///./archive.db"),
    ],
)
def test_to_sync_url(raw: str, expected: str) -> None:
    assert to_sync_url(raw) == expected


def test_query_string_and_credentials_survive() -> None:
    """sslmode is not optional on Neon — dropping it would break TLS."""
    assert to_async_url(NEON).endswith("/archive?sslmode=require")
    assert "user:pw@" in to_async_url(NEON)


def test_database_normalizes_at_construction() -> None:
    """The CLI passes settings.database_url straight in; it must self-correct."""
    from archiver.storage.db import Database

    assert Database("sqlite:///:memory:").url == "sqlite+aiosqlite:///:memory:"
