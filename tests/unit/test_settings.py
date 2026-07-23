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
    assert s.enable_auth is False
    assert s.enable_html_fallback is False
    assert s.download_media is False


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


def test_auth_requires_token(monkeypatch):
    monkeypatch.delenv("AUTH_TOKEN", raising=False)
    with pytest.raises(ValidationError):
        _load(monkeypatch, ARCHIVER_ENV="test", ENABLE_AUTH="true")


def test_auth_with_token_ok(monkeypatch):
    s = _load(monkeypatch, ARCHIVER_ENV="test", ENABLE_AUTH="true", AUTH_TOKEN="secret")
    assert s.enable_auth is True


def test_html_fallback_cannot_disable_robots(monkeypatch):
    with pytest.raises(ValidationError):
        _load(
            monkeypatch,
            ARCHIVER_ENV="test",
            ENABLE_HTML_FALLBACK="true",
            RESPECT_ROBOTS="false",
        )


def test_masked_dict_hides_secrets(monkeypatch):
    s = _load(
        monkeypatch,
        ARCHIVER_ENV="test",
        DATABASE_URL="postgresql://user:supersecret@host:5432/db",
        ENABLE_AUTH="true",
        AUTH_TOKEN="tok_abc123",
    )
    masked = s.masked_dict()
    assert "supersecret" not in masked["database_url"]
    assert masked["auth_token"] == "***set***"


def test_bad_log_level_rejected(monkeypatch):
    with pytest.raises(ValidationError):
        _load(monkeypatch, ARCHIVER_ENV="test", LOG_LEVEL="LOUD")
