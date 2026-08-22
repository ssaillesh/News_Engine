"""Settings for the research backend.

Reads the repo-root ``.env`` — the same file the archiver uses — so one
database URL and one Redis URL serve both apps. Values never appear in code;
add new ones here and to ``.env.example``.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Research-backend configuration."""

    model_config = SettingsConfigDict(
        env_file=_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",  # the archiver's vars share this file
    )

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5433/archive"
    redis_url: str = "redis://localhost:6379/0"
    api_title: str = "Stock Research API"
    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    """Cached settings — read the environment once per process."""
    return Settings()
