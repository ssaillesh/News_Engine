"""Typed exceptions for the HTTP client layer.

The hierarchy lets callers distinguish *retriable transport problems* from
*semantic* outcomes (not-found, auth, blocked) so the scheduler/orchestrator can
react correctly (DESIGN.md §9): retry with backoff vs. mark-deleted vs. enter a
DEGRADED state and alert.
"""

from __future__ import annotations


class ClientError(Exception):
    """Base class for all client-layer errors."""

    def __init__(self, message: str, *, status: int | None = None, url: str | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.url = url


class NetworkError(ClientError):
    """Transport failure (DNS, connection reset, TLS) after retries exhausted."""


class TimeoutError_(ClientError):  # noqa: N801 - avoid shadowing builtins.TimeoutError
    """Request timed out after retries exhausted."""


class RateLimitError(ClientError):
    """Rate limited (HTTP 429) and retries/Retry-After budget exhausted."""


class ServerError(ClientError):
    """Upstream 5xx after retries exhausted."""


class NotFoundError(ClientError):
    """Resource is gone (HTTP 404/410). Semantic — used for deletion detection."""


class AuthError(ClientError):
    """Unauthorized/forbidden (HTTP 401/403) that is *not* an anti-bot block."""


class BlockedError(ClientError):
    """Access blocked by an anti-bot / access-control barrier (e.g. Cloudflare).

    Raised on detection so the system can DEGRADE and alert rather than retry or
    attempt circumvention. This is intentionally terminal and non-retriable —
    circumventing an access-control measure is explicitly out of scope
    (DESIGN.md §1.8, docs/adr/0003, docs/adr/0004).
    """
