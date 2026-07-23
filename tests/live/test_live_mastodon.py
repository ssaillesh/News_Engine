"""Opt-in live smoke test against a real, permitted Mastodon instance.

Skipped by default. Enable with ``RUN_LIVE=1``. Targets mastodon.social (which
serves public API reads without auth) — NOT Truth Social. This validates the
client end-to-end against a real Mastodon API without any anti-bot evasion and at
a polite rate. Override target via ``LIVE_INSTANCE`` / ``LIVE_ACCT``.
"""

from __future__ import annotations

import os

import pytest

from archiver.clients import MastodonClient
from archiver.clients.rate_limit import TokenBucket

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LIVE") != "1", reason="live network test; set RUN_LIVE=1 to run"
)

INSTANCE = os.environ.get("LIVE_INSTANCE", "https://mastodon.social")
ACCT = os.environ.get("LIVE_ACCT", "Gargron")


async def test_live_lookup_and_paginate() -> None:
    async with MastodonClient(
        INSTANCE,
        user_agent="ts-archiver-live-test/0.1 (+personal-research)",
        rate_limiter=TokenBucket(1.0),  # polite: 1 req/sec
    ) as client:
        account = await client.lookup_account(ACCT)
        assert account["id"]
        assert account["username"]

        ids: list[str] = []
        async for status in client.iter_account_statuses(
            account["id"], limit=5, max_pages=2
        ):
            ids.append(status["id"])

        assert ids, "expected at least one status"
        assert len(ids) == len(set(ids)), "pagination must not duplicate statuses"
