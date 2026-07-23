"""Tests for secret scrubbing in logging."""

from __future__ import annotations

import pytest

from archiver.config.logging import mask_url, scrub


@pytest.mark.parametrize(
    "raw, secret",
    [
        ("Authorization: Bearer abc123XYZ", "abc123XYZ"),
        ("authorization=bearer tok_9f8a", "tok_9f8a"),
        ("using Bearer eyJhbGciOi.payload.sig now", "eyJhbGciOi.payload.sig"),
        ("access_token=super_secret_value", "super_secret_value"),
        ("api_key: KEY-123-456", "KEY-123-456"),
        ("password=hunter2", "hunter2"),
    ],
)
def test_scrub_removes_secret(raw: str, secret: str):
    out = scrub(raw)
    assert secret not in out
    assert "[REDACTED]" in out


def test_scrub_masks_url_credentials():
    out = scrub("postgresql://user:supersecret@db:5432/archive")
    assert "supersecret" not in out
    assert "user:" in out  # username is preserved; only the password is hidden


def test_scrub_is_noop_on_clean_text():
    clean = "Ingested 40 statuses in 1.2s (frontier_lag=3s)"
    assert scrub(clean) == clean


def test_mask_url_preserves_shape():
    masked = mask_url("redis://:mypw@localhost:6379/0")
    assert "mypw" not in masked
    assert masked.startswith("redis://")
