"""Tests for the layered configuration system."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from archiver.config import settings as settings_mod


def _load(monkeypatch, **env: str):
    # Neutralize any developer .env on disk so tests are hermetic.
    monkeypatch.setenv("ARCHIVER_ENV_FILE", "/nonexistent.env")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    settings_mod.get_settings.cache_clear()
    return settings_mod.get_settings()


def test_conservative_defaults(monkeypatch):
    s = _load(monkeypatch, ARCHIVER_ENV="test")
    assert s.env == "test"
    assert s.respect_robots is True
    assert s.sentiment_model == "ProsusAI/finbert"


def test_env_overrides_profile_yaml(monkeypatch):
    # dev.yaml sets min_poll_interval_s: 30; env must win.
    s = _load(monkeypatch, ARCHIVER_ENV="dev", MIN_POLL_INTERVAL_S="7")
    assert s.min_poll_interval_s == 7


def test_profile_yaml_overrides_defaults(monkeypatch):
    # test.yaml sets an in-memory sqlite URL, differing from the field default.
    s = _load(monkeypatch, ARCHIVER_ENV="test")
    assert s.database_url == "sqlite+aiosqlite:///:memory:"


def test_interval_ordering_is_validated(monkeypatch):
    with pytest.raises(ValidationError):
        _load(
            monkeypatch,
            ARCHIVER_ENV="test",
            MIN_POLL_INTERVAL_S="1000",
            MAX_POLL_INTERVAL_S="10",
        )


def test_masked_dict_hides_secrets(monkeypatch):
    s = _load(
        monkeypatch,
        ARCHIVER_ENV="test",
        DATABASE_URL="postgresql://user:supersecret@host:5432/db",
        GOVINFO_API_KEY="real_key_abc123",
    )
    masked = s.masked_dict()
    assert "supersecret" not in masked["database_url"]
    assert masked["govinfo_api_key"] == "***set***"


def test_masked_dict_shows_the_public_demo_key(monkeypatch):
    # DEMO_KEY is the shared public default — masking it would hide useful signal.
    s = _load(monkeypatch, ARCHIVER_ENV="test")
    assert s.masked_dict()["govinfo_api_key"] == "DEMO_KEY"


def test_bad_log_level_rejected(monkeypatch):
    with pytest.raises(ValidationError):
        _load(monkeypatch, ARCHIVER_ENV="test", LOG_LEVEL="LOUD")
