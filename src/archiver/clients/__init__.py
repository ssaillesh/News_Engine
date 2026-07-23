"""HTTP client layer — the shared transport every source adapter builds on.

This layer is the *only* place that touches the network (DESIGN.md §2.2). It
handles retries, backoff, and rate limiting, and contains **no** anti-bot
evasion. If it hits an access-control barrier (e.g. a Cloudflare 403 challenge),
it *detects and surfaces* that as ``BlockedError`` and stops — it does not try to
circumvent it (DESIGN.md §1.8, §9; docs/adr/0004).
"""

from archiver.clients.base import ApiResponse, BaseHttpClient
from archiver.clients.exceptions import (
    AuthError,
    BlockedError,
    ClientError,
    NetworkError,
    NotFoundError,
    RateLimitError,
    ServerError,
)

__all__ = [
    "ApiResponse",
    "AuthError",
    "BaseHttpClient",
    "BlockedError",
    "ClientError",
    "NetworkError",
    "NotFoundError",
    "RateLimitError",
    "ServerError",
]
