"""Shared pytest fixtures."""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import pytest

from archiver.storage.db import Database

_FIXTURE_DIRS = (Path(__file__).parent / "sources" / "fixtures",)


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    """Ensure each test resolves settings freshly (the singleton is cached)."""
    from archiver.config import settings as settings_mod

    settings_mod.get_settings.cache_clear()
    yield
    settings_mod.get_settings.cache_clear()


@pytest.fixture
def load_fixture() -> Callable[[str], Any]:
    """Load a recorded JSON fixture by name from any known fixtures directory."""

    def _load(name: str) -> Any:
        for directory in _FIXTURE_DIRS:
            path = directory / name
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
        raise FileNotFoundError(f"fixture {name!r} not found in {_FIXTURE_DIRS}")

    return _load


@pytest.fixture
def load_text_fixture() -> Callable[[str], str]:
    """Load a non-JSON fixture (e.g. RSS XML) as raw text."""

    def _load(name: str) -> str:
        for directory in _FIXTURE_DIRS:
            path = directory / name
            if path.exists():
                return path.read_text(encoding="utf-8")
        raise FileNotFoundError(f"fixture {name!r} not found in {_FIXTURE_DIRS}")

    return _load


def _make_db() -> Database:
    """Postgres when TEST_DATABASE_URL is set, otherwise in-memory SQLite."""
    url = os.environ.get("TEST_DATABASE_URL")
    return Database(url) if url else Database.in_memory()


@pytest.fixture
async def db() -> AsyncIterator[Database]:
    database = _make_db()
    await database.drop_all()  # checkfirst=True → safe on an empty DB
    await database.create_all()
    try:
        yield database
    finally:
        await database.drop_all()
        await database.dispose()
