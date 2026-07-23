"""Contract tests for MastodonClient using respx-mocked HTTP (no real network).

Covers the transport behaviors DESIGN.md §7/§9 require: pagination (Link header
and manual fallback), 429/Retry-After retry, 5xx retry, 404 → NotFoundError,
Cloudflare 403 challenge → BlockedError (terminal, no retry), JSON 403 → AuthError,
and network-error retry.
"""

from __future__ import annotations

import random

import httpx
import pytest
import respx

from archiver.clients import (
    AuthError,
    BlockedError,
    MastodonClient,
    NetworkError,
    NotFoundError,
)
from archiver.clients.rate_limit import NullRateLimiter

BASE = "https://mastodon.example"
STATUSES = f"{BASE}/api/v1/accounts/1/statuses"


async def _noop_sleep(_seconds: float) -> None:
    return None


def make_client(**over) -> MastodonClient:
    params = {
        "user_agent": "test-agent",
        "max_retries": 3,
        "backoff_base_s": 0.001,
        "backoff_cap_s": 0.001,
        "rate_limiter": NullRateLimiter(),
        "sleep": _noop_sleep,
        "rng": random.Random(0),
    }
    params.update(over)
    return MastodonClient(BASE, **params)


@respx.mock
async def test_lookup_account_returns_json():
    respx.get(f"{BASE}/api/v1/accounts/lookup").mock(
        return_value=httpx.Response(200, json={"id": "1", "username": "realDonaldTrump"})
    )
    async with make_client() as client:
        account = await client.lookup_account("realDonaldTrump")
    assert account["id"] == "1"


@respx.mock
async def test_pagination_follows_link_header():
    route = respx.get(STATUSES).mock(
        side_effect=[
            httpx.Response(
                200,
                json=[{"id": "3"}, {"id": "2"}],
                headers={"Link": f'<{STATUSES}?max_id=2>; rel="next"'},
            ),
            httpx.Response(200, json=[]),  # empty page ends iteration
        ]
    )
    async with make_client() as client:
        ids = [s["id"] async for s in client.iter_account_statuses("1")]
    assert ids == ["3", "2"]
    assert route.call_count == 2


@respx.mock
async def test_pagination_manual_fallback_uses_max_id():
    route = respx.get(STATUSES).mock(
        side_effect=[
            httpx.Response(200, json=[{"id": "3"}, {"id": "2"}]),  # no Link header
            httpx.Response(200, json=[{"id": "1"}]),
            httpx.Response(200, json=[]),
        ]
    )
    async with make_client() as client:
        ids = [s["id"] async for s in client.iter_account_statuses("1")]
    assert ids == ["3", "2", "1"]
    # second request should carry max_id=2 (oldest of page 1), third max_id=1
    assert route.calls[1].request.url.params.get("max_id") == "2"
    assert route.calls[2].request.url.params.get("max_id") == "1"


@respx.mock
async def test_429_retry_after_then_success():
    route = respx.get(f"{BASE}/api/v1/statuses/9").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "0"}, json={"error": "slow down"}),
            httpx.Response(200, json={"id": "9"}),
        ]
    )
    async with make_client() as client:
        status = await client.get_status("9")
    assert status["id"] == "9"
    assert route.call_count == 2


@respx.mock
async def test_5xx_retry_then_success():
    route = respx.get(f"{BASE}/api/v1/statuses/9").mock(
        side_effect=[
            httpx.Response(503, json={"error": "oops"}),
            httpx.Response(200, json={"id": "9"}),
        ]
    )
    async with make_client() as client:
        status = await client.get_status("9")
    assert status["id"] == "9"
    assert route.call_count == 2


@respx.mock
async def test_cloudflare_403_is_blocked_and_not_retried():
    route = respx.get(f"{BASE}/api/v1/statuses/9").mock(
        return_value=httpx.Response(
            403,
            headers={"server": "cloudflare", "cf-ray": "abc123", "content-type": "text/html"},
            text="<!DOCTYPE html><html>Just a moment...</html>",
        )
    )
    async with make_client() as client:
        with pytest.raises(BlockedError):
            await client.get_status("9")
    assert route.call_count == 1  # terminal: detected and halted, never circumvented


@respx.mock
async def test_json_403_is_auth_error_not_blocked():
    respx.get(f"{BASE}/api/v1/statuses/9").mock(
        return_value=httpx.Response(403, json={"error": "This action is not allowed"})
    )
    async with make_client() as client:
        with pytest.raises(AuthError):
            await client.get_status("9")


@respx.mock
async def test_404_raises_not_found():
    respx.get(f"{BASE}/api/v1/statuses/gone").mock(
        return_value=httpx.Response(404, json={"error": "Record not found"})
    )
    async with make_client() as client:
        with pytest.raises(NotFoundError):
            await client.get_status("gone")


@respx.mock
async def test_network_error_retries_then_succeeds():
    route = respx.get(f"{BASE}/api/v1/statuses/9").mock(
        side_effect=[httpx.ConnectError("boom"), httpx.Response(200, json={"id": "9"})]
    )
    async with make_client() as client:
        status = await client.get_status("9")
    assert status["id"] == "9"
    assert route.call_count == 2


@respx.mock
async def test_network_error_exhausts_retries():
    respx.get(f"{BASE}/api/v1/statuses/9").mock(side_effect=httpx.ConnectError("boom"))
    async with make_client(max_retries=2) as client:
        with pytest.raises(NetworkError):
            await client.get_status("9")
