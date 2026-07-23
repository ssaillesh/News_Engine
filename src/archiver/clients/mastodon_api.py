"""Mastodon-compatible REST API client (DESIGN.md §5.1–§5.7).

Typed methods over the endpoints the archiver needs — account lookup, an account's
statuses (with cursor pagination), and a status's conversation context. Returns
raw JSON (dicts/lists) which the Phase 4 parser validates and the raw store
captures verbatim. Provider-agnostic: point ``api_base_url`` at any instance you
are authorized to access.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any, cast

from archiver.clients.base import ApiResponse, BaseHttpClient
from archiver.clients.pagination import next_cursor_params, parse_link_header
from archiver.clients.rate_limit import RateLimiter, TokenBucket

if TYPE_CHECKING:
    from archiver.config.settings import Settings


class MastodonClient(BaseHttpClient):
    @classmethod
    def from_settings(
        cls, settings: Settings, *, rate_limiter: RateLimiter | None = None
    ) -> MastodonClient:
        return cls(
            settings.api_base_url,
            user_agent=settings.user_agent,
            timeout_s=settings.http_timeout_s,
            max_retries=settings.http_max_retries,
            backoff_base_s=settings.backoff_base_s,
            backoff_cap_s=settings.backoff_cap_s,
            auth_token=settings.auth_token if settings.enable_auth else None,
            rate_limiter=rate_limiter or TokenBucket(settings.rate_limit_rps),
        )

    # ── single-object reads ───────────────────────────────────────────────────
    async def lookup_account(self, acct: str) -> dict[str, Any]:
        """Resolve a handle to its account object (stable ``id`` is the durable key)."""
        resp = await self.get_json("/api/v1/accounts/lookup", params={"acct": acct})
        return cast(dict[str, Any], resp.data)

    async def get_account(self, account_id: str) -> dict[str, Any]:
        resp = await self.get_json(f"/api/v1/accounts/{account_id}")
        return cast(dict[str, Any], resp.data)

    async def get_status(self, status_id: str) -> dict[str, Any]:
        resp = await self.get_json(f"/api/v1/statuses/{status_id}")
        return cast(dict[str, Any], resp.data)

    async def status_context(self, status_id: str) -> dict[str, Any]:
        """Return ``{"ancestors": [...], "descendants": [...]}`` for a status."""
        resp = await self.get_json(f"/api/v1/statuses/{status_id}/context")
        return cast(dict[str, Any], resp.data)

    # ── paginated reads ───────────────────────────────────────────────────────
    async def account_statuses(
        self,
        account_id: str,
        *,
        limit: int = 40,
        max_id: str | None = None,
        since_id: str | None = None,
        min_id: str | None = None,
        exclude_replies: bool = False,
        exclude_reblogs: bool = False,
        only_media: bool = False,
        pinned: bool = False,
    ) -> ApiResponse:
        """Fetch a single page of an account's statuses (newest-first)."""
        params: dict[str, Any] = {"limit": limit}
        if max_id:
            params["max_id"] = max_id
        if since_id:
            params["since_id"] = since_id
        if min_id:
            params["min_id"] = min_id
        if exclude_replies:
            params["exclude_replies"] = "true"
        if exclude_reblogs:
            params["exclude_reblogs"] = "true"
        if only_media:
            params["only_media"] = "true"
        if pinned:
            params["pinned"] = "true"
        return await self.get_json(f"/api/v1/accounts/{account_id}/statuses", params=params)

    async def iter_account_statuses(
        self,
        account_id: str,
        *,
        direction: str = "backfill",
        limit: int = 40,
        max_id: str | None = None,
        since_id: str | None = None,
        min_id: str | None = None,
        exclude_replies: bool = False,
        exclude_reblogs: bool = False,
        max_pages: int | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield statuses across pages.

        ``direction="backfill"`` walks toward older posts (``Link rel=next`` /
        ``max_id``); ``direction="forward"`` walks toward newer posts
        (``Link rel=prev`` / ``min_id``) for steady-state monitoring.
        """
        if direction not in ("backfill", "forward"):
            raise ValueError(f"direction must be 'backfill' or 'forward', got {direction!r}")
        follow = "next" if direction == "backfill" else "prev"

        params: dict[str, Any] = {"limit": limit}
        if max_id:
            params["max_id"] = max_id
        if since_id:
            params["since_id"] = since_id
        if min_id:
            params["min_id"] = min_id
        if exclude_replies:
            params["exclude_replies"] = "true"
        if exclude_reblogs:
            params["exclude_reblogs"] = "true"

        path = f"/api/v1/accounts/{account_id}/statuses"
        page = 0
        resp = await self.get_json(path, params=params)
        while True:
            items = resp.data
            if not isinstance(items, list) or not items:
                return
            for item in items:
                yield item
            page += 1
            if max_pages is not None and page >= max_pages:
                return
            links = parse_link_header(resp.headers.get("link"))
            target = links.get(follow)
            if target:
                resp = await self.get_json(target)  # opaque absolute cursor URL
            else:
                cursor = next_cursor_params(items, follow=follow)
                if not cursor:
                    return
                resp = await self.get_json(path, params={**params, **cursor})
