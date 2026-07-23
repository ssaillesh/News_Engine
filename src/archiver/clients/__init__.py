"""HTTP client layer — a provider-agnostic Mastodon-compatible API client.

This layer is the *only* place that touches the network (DESIGN.md §2.2). It is
deliberately generic: it speaks the Mastodon REST API and can be pointed at any
instance the operator is authorized to access. It contains **no** anti-bot
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
from archiver.clients.mastodon_api import MastodonClient

__all__ = [
    "ApiResponse",
    "AuthError",
    "BaseHttpClient",
    "BlockedError",
    "ClientError",
    "MastodonClient",
    "NetworkError",
    "NotFoundError",
    "RateLimitError",
    "ServerError",
]
