"""Federal Register ingester — Trump's official presidential documents.

The Federal Register publishes presidential documents (executive orders,
proclamations, memoranda, notices) via a free, open, machine-readable API. US
government works are public domain and the API imposes no anti-bot barrier, so
this is a fully compliant *live* first-party source for "what Trump puts out" in
his official capacity — the counterpart to the blocked Truth Social social feed.

Docs: https://www.federalregister.gov/developers/documentation/api/v1
"""

from __future__ import annotations

import html as html_lib
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from archiver.clients.base import BaseHttpClient
from archiver.clients.rate_limit import RateLimiter, TokenBucket
from archiver.domain.hashing import content_hash, payload_hash
from archiver.storage.repositories import (
    AccountRepository,
    CheckpointRepository,
    RawPayloadRepository,
    StatusRepository,
)

if TYPE_CHECKING:
    from archiver.config.settings import Settings
    from archiver.storage.db import Database

SOURCE = "federal_register"

# Fields requested from the API (verified valid; enriches the default set).
_FIELDS = (
    "document_number",
    "title",
    "type",
    "subtype",
    "abstract",
    "publication_date",
    "signing_date",
    "executive_order_number",
    "president",
    "citation",
    "html_url",
    "pdf_url",
    "body_html_url",
    "full_text_xml_url",
)

# Synthetic account representing Trump's official presidential-document output.
TRUMP_ACCOUNT: dict[str, Any] = {
    "id": "fr:donald-trump",
    "username": "realDonaldTrump",
    "acct": "donald-trump@federalregister.gov",
    "display_name": "Donald J. Trump — Presidential Documents",
    "url": "https://www.federalregister.gov/presidents/donald-trump",
}


class FederalRegisterClient(BaseHttpClient):
    BASE_URL = "https://www.federalregister.gov"

    @classmethod
    def from_settings(
        cls, settings: Settings, *, rate_limiter: RateLimiter | None = None
    ) -> FederalRegisterClient:
        return cls(
            cls.BASE_URL,
            user_agent=settings.user_agent,
            timeout_s=settings.http_timeout_s,
            max_retries=settings.http_max_retries,
            backoff_base_s=settings.backoff_base_s,
            backoff_cap_s=settings.backoff_cap_s,
            rate_limiter=rate_limiter or TokenBucket(settings.rate_limit_rps),
        )

    async def iter_presidential_documents(
        self,
        *,
        president: str = "donald-trump",
        since: str | None = None,
        per_page: int = 100,
        max_pages: int | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield presidential-document objects newest-first.

        ``since`` is an ISO date (YYYY-MM-DD); only documents published on/after it
        are returned — the basis for incremental ingestion.
        """
        params: list[tuple[str, Any]] = [
            ("per_page", per_page),
            ("order", "newest"),
            ("conditions[president][]", president),
            ("conditions[type][]", "PRESDOCU"),
            *[("fields[]", field) for field in _FIELDS],
        ]
        if since:
            params.append(("conditions[publication_date][gte]", since))

        resp = await self.get_json("/api/v1/documents.json", params=params)
        page = 0
        while True:
            data = resp.data
            results = data.get("results", []) if isinstance(data, dict) else []
            for document in results:
                yield document
            page += 1
            if max_pages is not None and page >= max_pages:
                return
            next_url = data.get("next_page_url") if isinstance(data, dict) else None
            if not next_url:
                return
            resp = await self.get_json(next_url)  # absolute cursor URL


def _publication_datetime(document: dict[str, Any]) -> datetime:
    for key in ("publication_date", "signing_date"):
        value = document.get(key)
        if value:
            try:
                return datetime.fromisoformat(value).replace(tzinfo=UTC)
            except ValueError:
                continue
    return datetime.now(UTC)


def normalize_document(document: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Map a Federal Register document into (account_row, status_row) dicts."""
    document_number = document["document_number"]
    title = (document.get("title") or "").strip()
    abstract = (document.get("abstract") or "").strip()
    kind = document.get("subtype") or document.get("type") or "Presidential Document"

    text_parts = [f"[{kind}] {title}".strip()]
    if abstract:
        text_parts.append(abstract)
    content_text = "\n\n".join(text_parts)

    html_parts = [f"<p>{html_lib.escape(title)}</p>"] if title else []
    if abstract:
        html_parts.append(f"<p>{html_lib.escape(abstract)}</p>")
    content_html = "".join(html_parts) or None

    status_row = {
        "id": f"fr:{document_number}",
        "account_id": TRUMP_ACCOUNT["id"],
        "created_at": _publication_datetime(document),
        "url": document.get("html_url"),
        "uri": document.get("html_url"),
        "content_html": content_html,
        "content_text": content_text,
        "content_hash": content_hash(content=content_text),
        "kind": kind,
        "visibility": "public",
        "source": SOURCE,
        "raw": document,
    }
    return dict(TRUMP_ACCOUNT), status_row


async def _read_checkpoint_since(db: Database) -> str | None:
    async with db.session() as session:
        checkpoint = await CheckpointRepository(session, db.dialect).get(TRUMP_ACCOUNT["id"])
        return checkpoint.frontier_cursor if checkpoint else None


async def _save_checkpoint(db: Database, latest_date: str) -> None:
    async with db.session() as session, session.begin():
        await AccountRepository(session, db.dialect).upsert(dict(TRUMP_ACCOUNT))
        await CheckpointRepository(session, db.dialect).upsert(
            {
                "target_account_id": TRUMP_ACCOUNT["id"],
                "phase": "monitor",
                "frontier_cursor": latest_date,
            }
        )


async def ingest_federal_register(
    db: Database,
    *,
    settings: Settings,
    since: str | None = None,
    max_pages: int | None = None,
    president: str = "donald-trump",
    rate_limiter: RateLimiter | None = None,
    incremental: bool = False,
) -> int:
    """Fetch presidential documents and upsert them into the archive.

    Idempotent: re-running never duplicates rows (natural-key upsert + raw-hash
    dedup). When ``incremental`` is set and no explicit ``since`` is given, only
    documents published on/after the last-seen publication date (from the
    checkpoint) are fetched, and the checkpoint is advanced afterward — this is
    what makes scheduled runs cheap. Returns the number of documents processed.
    """
    if incremental and since is None:
        since = await _read_checkpoint_since(db)

    processed = 0
    latest_date: str | None = since
    async with FederalRegisterClient.from_settings(settings, rate_limiter=rate_limiter) as client:
        async for document in client.iter_presidential_documents(
            president=president, since=since, max_pages=max_pages
        ):
            account_row, status_row = normalize_document(document)
            published = document.get("publication_date")
            if published and (latest_date is None or published > latest_date):
                latest_date = published
            async with db.session() as session, session.begin():
                await AccountRepository(session, db.dialect).upsert(account_row)
                await StatusRepository(session, db.dialect).upsert(status_row)
                await RawPayloadRepository(session, db.dialect).save(
                    {
                        "endpoint": "federal_register/documents",
                        "entity_type": "presidential_document",
                        "entity_id": status_row["id"],
                        "payload": document,
                        "payload_sha256": payload_hash(document),
                    }
                )
            processed += 1

    if incremental and processed and latest_date:
        await _save_checkpoint(db, latest_date)
    return processed
