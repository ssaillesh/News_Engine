"""Base async HTTP client: transport, retries, backoff, and block detection.

This is the single component that understands transport concerns (DESIGN.md §2.2,
§7.3, §9). It performs GET requests, paces them through a rate limiter, retries
*retriable* failures (network/timeout/429/5xx) with exponential backoff + full
jitter, and classifies terminal outcomes into typed exceptions. Crucially, it
*detects* an anti-bot access barrier (Cloudflare-style challenge) and raises
``BlockedError`` to halt — it never attempts to circumvent it.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, Self

import httpx

from archiver.clients.exceptions import (
    AuthError,
    BlockedError,
    ClientError,
    NetworkError,
    NotFoundError,
    RateLimitError,
    ServerError,
    TimeoutError_,
)
from archiver.clients.rate_limit import NullRateLimiter, RateLimiter

_MAX_RETRY_AFTER_S = 600.0

# Query params: a mapping, or a list of pairs (needed for repeated keys like
# the Federal Register API's ``conditions[president][]=…``).
QueryParams = Mapping[str, Any] | list[tuple[str, Any]]


@dataclass(slots=True)
class ApiResponse:
    """A successful API response plus the headers callers need for pagination."""

    data: Any
    headers: httpx.Headers
    status: int


def _parse_retry_after(response: httpx.Response) -> float | None:
    """Parse a ``Retry-After`` header (delta-seconds or HTTP-date) → seconds."""
    raw = response.headers.get("retry-after")
    if not raw:
        return None
    raw = raw.strip()
    if raw.isdigit():
        return min(float(raw), _MAX_RETRY_AFTER_S)
    try:
        when = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    delta = (when - datetime.now(UTC)).total_seconds()
    return min(max(delta, 0.0), _MAX_RETRY_AFTER_S)


class BaseHttpClient:
    def __init__(
        self,
        base_url: str,
        *,
        user_agent: str,
        timeout_s: float = 30.0,
        max_retries: int = 5,
        backoff_base_s: float = 1.0,
        backoff_cap_s: float = 60.0,
        rate_limiter: RateLimiter | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        rng: random.Random | None = None,
    ) -> None:
        self.max_retries = max_retries
        self.backoff_base = backoff_base_s
        self.backoff_cap = backoff_cap_s
        self._rate_limiter: RateLimiter = rate_limiter or NullRateLimiter()
        self._sleep = sleep
        self._rng = rng or random.Random()

        # Every source is public: we send no credentials at all.
        headers = {"User-Agent": user_agent, "Accept": "application/json"}
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers=headers,
            timeout=timeout_s,
            follow_redirects=True,
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    def _backoff(self, attempt: int) -> float:
        ceiling = min(self.backoff_cap, self.backoff_base * (2**attempt))
        return self._rng.uniform(0, ceiling)

    @staticmethod
    def _looks_blocked(response: httpx.Response) -> bool:
        """Detect an anti-bot / access-control challenge (e.g. Cloudflare).

        A genuine API error is JSON; a challenge is an HTML page served by the
        edge (Cloudflare markers + text/html). We only treat the latter as a
        block so real API 403/429/503 JSON responses flow through normal handling.
        """
        if response.status_code not in (403, 429, 503):
            return False
        headers = response.headers
        cloudflare = (
            "cloudflare" in headers.get("server", "").lower()
            or "cf-ray" in headers
            or "cf-mitigated" in headers
        )
        is_html = "text/html" in headers.get("content-type", "").lower()
        return cloudflare and is_html

    async def _send(
        self,
        method: str,
        url: str,
        *,
        params: QueryParams | None = None,
    ) -> httpx.Response:
        """Issue a request with retries/backoff, returning the successful response.

        Raises typed errors for terminal outcomes (blocked/auth/not-found/etc.).
        Shared by the JSON and text readers.
        """
        attempt = 0
        while True:
            await self._rate_limiter.acquire()
            try:
                response = await self._client.request(method, url, params=params)
            except httpx.TransportError as exc:
                if attempt >= self.max_retries:
                    if isinstance(exc, httpx.TimeoutException):
                        raise TimeoutError_(str(exc), url=url) from exc
                    raise NetworkError(str(exc), url=url) from exc
                await self._sleep(self._backoff(attempt))
                attempt += 1
                continue

            if self._looks_blocked(response):
                raise BlockedError(
                    f"Access blocked (HTTP {response.status_code}) by an anti-bot "
                    "barrier; halting rather than circumventing.",
                    status=response.status_code,
                    url=str(response.request.url),
                )

            code = response.status_code
            request_url = str(response.request.url)

            if code == 429:
                if attempt >= self.max_retries:
                    raise RateLimitError("rate limited", status=429, url=request_url)
                delay = _parse_retry_after(response)
                await self._sleep(delay if delay is not None else self._backoff(attempt))
                attempt += 1
                continue

            if 500 <= code < 600:
                if attempt >= self.max_retries:
                    raise ServerError(f"server error {code}", status=code, url=request_url)
                await self._sleep(self._backoff(attempt))
                attempt += 1
                continue

            if code in (404, 410):
                raise NotFoundError(f"not found ({code})", status=code, url=request_url)
            if code in (401, 403):
                raise AuthError(f"unauthorized ({code})", status=code, url=request_url)
            if code >= 400:
                raise ClientError(f"unexpected status {code}", status=code, url=request_url)

            return response

    async def request_json(
        self,
        method: str,
        url: str,
        *,
        params: QueryParams | None = None,
    ) -> ApiResponse:
        response = await self._send(method, url, params=params)
        try:
            data = response.json()
        except ValueError as exc:
            raise ClientError(
                "non-JSON response body",
                status=response.status_code,
                url=str(response.request.url),
            ) from exc
        return ApiResponse(data=data, headers=response.headers, status=response.status_code)

    async def request_text(
        self,
        method: str,
        url: str,
        *,
        params: QueryParams | None = None,
    ) -> str:
        response = await self._send(method, url, params=params)
        return response.text

    async def get_json(self, url: str, *, params: QueryParams | None = None) -> ApiResponse:
        return await self.request_json("GET", url, params=params)

    async def get_text(self, url: str, *, params: QueryParams | None = None) -> str:
        return await self.request_text("GET", url, params=params)
