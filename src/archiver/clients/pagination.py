"""Mastodon pagination helpers (DESIGN.md §5.3).

Mastodon returns an RFC 5988 ``Link`` header with ``rel="next"`` (older, via
``max_id``) and ``rel="prev"`` (newer, via ``min_id``). Following those opaque
cursors is the robust path; when the header is absent we fall back to manual
cursoring off the first/last item ID (IDs are time-sortable snowflakes).
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, urlparse

_LINK_RE = re.compile(r'<(?P<url>[^>]+)>\s*;\s*rel="(?P<rel>[^"]+)"')


def parse_link_header(value: str | None) -> dict[str, str]:
    """Parse a ``Link`` header into ``{rel: url}`` (e.g. ``{"next": "...", "prev": "..."}``)."""
    if not value:
        return {}
    return {m.group("rel"): m.group("url") for m in _LINK_RE.finditer(value)}


def query_param(url: str, key: str) -> str | None:
    """Return a single query-parameter value from a URL, or None."""
    values = parse_qs(urlparse(url).query).get(key)
    return values[0] if values else None


def next_cursor_params(items: list[dict[str, Any]], *, follow: str) -> dict[str, str]:
    """Manual-fallback cursor when no ``Link`` header is present.

    Results are newest-first, so:
      * ``follow="next"`` (older) → ``max_id`` = last (oldest) item's id.
      * ``follow="prev"`` (newer) → ``min_id`` = first (newest) item's id.
    """
    if not items:
        return {}
    if follow == "next":
        return {"max_id": str(items[-1]["id"])}
    if follow == "prev":
        return {"min_id": str(items[0]["id"])}
    raise ValueError(f"unknown follow direction {follow!r}")
