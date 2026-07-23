"""Anti-corruption parsing layer (DESIGN.md §1.6, §8).

Validates raw Mastodon JSON against version-tolerant Pydantic schemas, then
normalizes it into storage-ready row dicts. Isolates the rest of the system from
upstream schema drift: when the API shape shifts, only this package changes.
"""

from archiver.parsing.normalizers import (
    NormalizedStatus,
    normalize_account,
    normalize_status,
)
from archiver.parsing.schemas import (
    AccountSchema,
    ContextSchema,
    StatusSchema,
    parse_account,
    parse_context,
    parse_status,
)

__all__ = [
    "AccountSchema",
    "ContextSchema",
    "NormalizedStatus",
    "StatusSchema",
    "normalize_account",
    "normalize_status",
    "parse_account",
    "parse_context",
    "parse_status",
]
