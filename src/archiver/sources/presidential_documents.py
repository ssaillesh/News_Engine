"""Compilation of Presidential Documents ingester — Trump's remarks & statements.

GovInfo's "Compilation of Presidential Documents" (CPD, collection code ``CPD``)
is the official first-party record of the President's public words: remarks,
exchanges with reporters, statements, messages, letters, and signed actions. It's
served by a free, machine-readable government API (api.govinfo.gov, fronted by
api.data.gov) — a fully compliant *live* source of Trump himself.

Docs: https://api.govinfo.gov/docs/  ·  Collection: https://www.govinfo.gov/app/collection/cpd
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from archiver.clients.base import BaseHttpClient
from archiver.clients.rate_limit import RateLimiter, TokenBucket
from archiver.domain.hashing import content_hash, payload_hash
from archiver.storage.repositories import (
    AccountRepository,
    RawPayloadRepository,
    StatusRepository,
)

if TYPE_CHECKING:
    from archiver.config.settings import Settings
    from archiver.storage.db import Database

SOURCE = "presidential_documents"

# Friendly "kind" derived from the document title prefix (CPD titles are typed).
_KIND_RE = re.compile(
    r"^(Remarks|Statement|Message|Letter|Interview|Address|Proclamation|"
    r"Executive Order|Memorandum|Notice|Nominations|Digest|Checklist|"
    r"Acts Approved|The President's News Conference)",
)

TRUMP_ACCOUNT: dict[str, Any] = {
    "id": "pd:donald-trump",
    "username": "realDonaldTrump",
    "acct": "donald-trump@govinfo.gov",
    "display_name": "Donald J. Trump — Presidential Documents",
    "url": "https://www.govinfo.gov/app/collection/cpd",
}


class GovInfoClient(BaseHttpClient):
    BASE_URL = "https://api.govinfo.gov"

    def __init__(self, base_url: str, *, api_key: str, **kwargs: Any) -> None:
        super().__init__(base_url, **kwargs)
        # api.data.gov accepts the key via header (kept out of URLs/logs).
        self._client.headers["X-Api-Key"] = api_key

    @classmethod
    def from_settings(
        cls, settings: Settings, *, rate_limiter: RateLimiter | None = None
    ) -> GovInfoClient:
        return cls(
            cls.BASE_URL,
            api_key=settings.govinfo_api_key,
            user_agent=settings.user_agent,
            timeout_s=settings.http_timeout_s,
            max_retries=settings.http_max_retries,
            backoff_base_s=settings.backoff_base_s,
            backoff_cap_s=settings.backoff_cap_s,
            rate_limiter=rate_limiter or TokenBucket(settings.rate_limit_rps),
        )

    async def iter_cpd_packages(
        self,
        *,
        since: str,
        page_size: int = 100,
        max_pages: int | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield CPD package records published on/after ``since`` (YYYY-MM-DD)."""
        params: list[tuple[str, Any]] = [
            ("collection", "CPD"),
            ("pageSize", page_size),
            ("offsetMark", "*"),
        ]
        resp = await self.get_json(f"/published/{since}", params=params)
        page = 0
        while True:
            data = resp.data
            packages = data.get("packages", []) if isinstance(data, dict) else []
            for package in packages:
                yield package
            page += 1
            if max_pages is not None and page >= max_pages:
                return
            next_url = data.get("nextPage") if isinstance(data, dict) else None
            if not next_url or not packages:
                return
            resp = await self.get_json(next_url)  # absolute cursor URL (offsetMark)


def _issued_at(package: dict[str, Any]) -> datetime:
    value = package.get("dateIssued")
    if value:
        try:
            return datetime.fromisoformat(value).replace(tzinfo=UTC)
        except ValueError:
            pass
    return datetime.now(UTC)


def _kind(package: dict[str, Any]) -> str:
    title = package.get("title") or ""
    match = _KIND_RE.match(title)
    if match:
        return match.group(1)
    doc_class = package.get("docClass")
    return doc_class if isinstance(doc_class, str) else "Presidential Document"


def normalize_package(package: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Map a CPD package record into (account_row, status_row) dicts."""
    package_id = package["packageId"]
    title = (package.get("title") or "").strip()
    kind = _kind(package)

    status_row = {
        "id": f"cpd:{package_id}",
        "account_id": TRUMP_ACCOUNT["id"],
        "created_at": _issued_at(package),
        "url": f"https://www.govinfo.gov/app/details/{package_id}",
        "uri": package.get("packageLink"),
        "content_html": None,
        "content_text": title,
        "content_hash": content_hash(content=title),
        "kind": kind,
        "visibility": "public",
        "source": SOURCE,
        "raw": {**package, "kind": kind},
    }
    return dict(TRUMP_ACCOUNT), status_row


async def ingest_presidential_documents(
    db: Database,
    *,
    settings: Settings,
    since: str,
    max_pages: int | None = None,
    rate_limiter: RateLimiter | None = None,
) -> int:
    """Fetch CPD packages published on/after ``since`` and upsert them.

    Idempotent (packageId-keyed upsert + raw-hash dedup). Returns items processed.
    """
    processed = 0
    async with GovInfoClient.from_settings(settings, rate_limiter=rate_limiter) as client:
        async for package in client.iter_cpd_packages(since=since, max_pages=max_pages):
            account_row, status_row = normalize_package(package)
            async with db.session() as session, session.begin():
                await AccountRepository(session, db.dialect).upsert(account_row)
                await StatusRepository(session, db.dialect).upsert(status_row)
                await RawPayloadRepository(session, db.dialect).save(
                    {
                        "endpoint": "govinfo/published/CPD",
                        "entity_type": "presidential_document",
                        "entity_id": status_row["id"],
                        "payload": status_row["raw"],
                        "payload_sha256": payload_hash(status_row["raw"]),
                    }
                )
            processed += 1
    return processed
