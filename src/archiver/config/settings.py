"""Layered application configuration.

Precedence (highest wins):

    init args  >  environment variables  >  .env file  >  profile YAML  >  defaults

The active profile is chosen by ``ARCHIVER_ENV`` and loaded from
``config/profiles/<env>.yaml``. See DESIGN.md §11 for rationale.

Compliance switches default to the most conservative posture (DESIGN.md §1.8):
robots respected, no auth, public-only, no HTML fallback, media references only.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

_PROFILE_DIR = Path(__file__).parent / "profiles"
_LOG_LEVELS = {"TRACE", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


def _load_profile_yaml(profile: str) -> dict[str, Any]:
    """Load ``profiles/<profile>.yaml`` as a mapping (empty if absent)."""
    path = _PROFILE_DIR / f"{profile}.yaml"
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Profile {path} must be a YAML mapping, got {type(data).__name__}")
    return data


class _YamlProfileSource(PydanticBaseSettingsSource):
    """Settings source that injects values from the selected profile YAML.

    Keyed by field name; sits below env/.env and above field defaults.
    """

    def __init__(self, settings_cls: type[BaseSettings], data: dict[str, Any]) -> None:
        super().__init__(settings_cls)
        self._data = data

    def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:
        # Not used: __call__ returns the whole mapping at once.
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        return dict(self._data)


class Settings(BaseSettings):
    """Validated, immutable-at-runtime application settings."""

    model_config = SettingsConfigDict(
        env_file=os.environ.get("ARCHIVER_ENV_FILE", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── environment / identity ────────────────────────────────────────────────
    env: Literal["dev", "test", "prod"] = Field(
        "dev", validation_alias=AliasChoices("env", "ARCHIVER_ENV")
    )
    target_handle: str = Field("realDonaldTrump")

    # ── storage ───────────────────────────────────────────────────────────────
    database_url: str = Field("sqlite+aiosqlite:///./archive.db")
    redis_url: str | None = Field(None)

    # ── API client (provider-agnostic Mastodon-compatible) ────────────────────
    # Point at any Mastodon-compatible instance you are authorized to access.
    # NOT defaulted to truthsocial.com — Phase 0 confirmed it blocks anonymous
    # automated access at Cloudflare (see docs/adr/0004).
    api_base_url: str = Field("https://mastodon.social")
    user_agent: str = Field("ts-archiver/0.1 (+personal-research; contact-configured)")
    http_timeout_s: float = Field(30.0, gt=0)
    http_max_retries: int = Field(5, ge=0)
    backoff_base_s: float = Field(1.0, gt=0)
    backoff_cap_s: float = Field(60.0, gt=0)

    # ── web UI ────────────────────────────────────────────────────────────────
    # Default off 8000 to avoid the common collision with other local dev servers
    # / SSH tunnels. `serve` auto-skips to the next free port if this one is busy.
    web_host: str = Field("127.0.0.1")
    web_port: int = Field(8137, ge=1, le=65535)

    # ── scheduling / politeness ───────────────────────────────────────────────
    min_poll_interval_s: int = Field(60, ge=1)
    max_poll_interval_s: int = Field(1800, ge=1)
    rate_limit_rps: float = Field(0.5, gt=0)

    # ── compliance switches (conservative by default; DESIGN.md §1.8) ─────────
    respect_robots: bool = Field(True)
    enable_html_fallback: bool = Field(False)
    enable_auth: bool = Field(False)
    download_media: bool = Field(False)
    archive_foreign_replies: bool = Field(False)

    # ── secrets (never logged; scrubbed everywhere) ───────────────────────────
    auth_token: str | None = Field(None, repr=False)
    # Free key from https://api.data.gov/signup/ (DEMO_KEY works but is rate-limited).
    govinfo_api_key: str = Field("DEMO_KEY", repr=False)

    # ── observability ─────────────────────────────────────────────────────────
    log_level: str = Field("INFO")
    log_json: bool = Field(False)

    # ── validation ────────────────────────────────────────────────────────────
    @model_validator(mode="after")
    def _validate(self) -> Settings:
        self.log_level = self.log_level.upper()
        if self.log_level not in _LOG_LEVELS:
            raise ValueError(f"log_level must be one of {sorted(_LOG_LEVELS)}")
        if self.min_poll_interval_s > self.max_poll_interval_s:
            raise ValueError("min_poll_interval_s must be <= max_poll_interval_s")
        if self.enable_auth and not self.auth_token:
            raise ValueError("enable_auth=True requires AUTH_TOKEN to be set")
        if self.enable_html_fallback and not self.respect_robots:
            # An explicit, refusable combination — force the operator to be deliberate.
            raise ValueError(
                "Refusing enable_html_fallback=True with respect_robots=False. "
                "Disabling robots enforcement is not permitted via config alone."
            )
        return self

    @property
    def is_prod(self) -> bool:
        return self.env == "prod"

    def masked_dict(self) -> dict[str, Any]:
        """Config for display: secrets and URL credentials redacted."""
        from archiver.config.logging import mask_url

        data = self.model_dump()
        data["auth_token"] = "***set***" if self.auth_token else None
        if self.database_url:
            data["database_url"] = mask_url(self.database_url)
        if self.redis_url:
            data["redis_url"] = mask_url(self.redis_url)
        return data

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        profile = os.environ.get("ARCHIVER_ENV", "dev")
        yaml_source = _YamlProfileSource(settings_cls, _load_profile_yaml(profile))
        # Order = priority, highest first.
        return (init_settings, env_settings, dotenv_settings, yaml_source, file_secret_settings)


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings singleton (cached)."""
    return Settings()
