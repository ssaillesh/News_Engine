"""Canonical hashing for deduplication and edit detection (DESIGN.md §5.8, §5.9).

``content_hash`` fingerprints only the *content-defining* fields of a status, so
that an edit changes it but volatile engagement counts do not. It must be
deterministic across processes and time — hence canonical JSON (sorted keys,
stable separators) over an explicit field set.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from typing import Any


def _canonical(payload: Any) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def content_hash(
    *,
    content: str | None,
    spoiler_text: str | None = None,
    sensitive: bool = False,
    media_ids: Iterable[str] = (),
    poll_options: list[str] | None = None,
) -> str:
    """SHA-256 over the content-defining fields of a status.

    Media IDs are sorted (order-independent); poll option order is preserved
    (order is meaningful). Engagement counts are intentionally excluded.
    """
    fingerprint = {
        "content": content or "",
        "spoiler": spoiler_text or "",
        "sensitive": bool(sensitive),
        "media": sorted(str(m) for m in media_ids),
        "poll": list(poll_options) if poll_options else [],
    }
    return hashlib.sha256(_canonical(fingerprint)).hexdigest()


def payload_hash(payload: Any) -> str:
    """Stable hash of an arbitrary JSON-serializable payload.

    Used for raw-capture dedup (``raw_payloads.payload_sha256``) and for detecting
    changed profile snapshots (``account_snapshots.content_hash``).
    """
    return hashlib.sha256(_canonical(payload)).hexdigest()


def sha256_hex(data: bytes) -> str:
    """SHA-256 of raw bytes (used for content-addressed media blobs)."""
    return hashlib.sha256(data).hexdigest()
