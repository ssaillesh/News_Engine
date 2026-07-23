"""Media attachment extraction (DESIGN.md §5.5).

Turns a status's media attachments into ``media``-table row dicts (reference
archival). Binary download/checksumming is a separate, opt-in concern (Phase 8).
"""

from __future__ import annotations

from typing import Any

from archiver.parsing.schemas import StatusSchema


def extract_media(status: StatusSchema) -> list[dict[str, Any]]:
    """Return one ``media``-row dict per attachment on the status."""
    return [
        {
            "id": attachment.id,
            "status_id": status.id,
            "type": attachment.type,
            "url": attachment.url,
            "preview_url": attachment.preview_url,
            "remote_url": attachment.remote_url,
            "description": attachment.description,
            "blurhash": attachment.blurhash,
            "meta": attachment.meta,
        }
        for attachment in status.media_attachments
    ]
