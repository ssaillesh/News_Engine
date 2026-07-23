"""Structured logging with secret scrubbing.

All log records pass through a scrubber that redacts credentials before they are
emitted, so tokens/passwords never reach stdout, files, or aggregators
(DESIGN.md §1.7, §10.1). Production emits JSON; dev emits human-readable lines.
"""

from __future__ import annotations

import re
import sys
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from loguru import Record

    from archiver.config.settings import Settings

# (pattern, replacement) pairs applied in order to every rendered message.
_SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Authorization header, with or without a Bearer prefix.
    (re.compile(r"(authorization\s*[:=]\s*)(bearer\s+)?\S+", re.IGNORECASE), r"\1\2[REDACTED]"),
    # Bare "Bearer <token>" anywhere.
    (re.compile(r"(bearer\s+)[A-Za-z0-9._\-]+", re.IGNORECASE), r"\1[REDACTED]"),
    # key/value secrets: token=, access_token:, api_key=, password:, secret=
    (
        re.compile(
            r"((?:auth[_-]?token|access[_-]?token|api[_-]?key|password|secret)"
            r"\s*[:=]\s*)([^\s,;&]+)",
            re.IGNORECASE,
        ),
        r"\1[REDACTED]",
    ),
    # Credentials embedded in URLs:  scheme://[user]:PASSWORD@host  (user may be empty)
    (re.compile(r"(://[^:/@\s]*:)[^@/\s]+(@)"), r"\1[REDACTED]\2"),
]


def scrub(text: str) -> str:
    """Redact known secret shapes from a string."""
    for pattern, repl in _SECRET_PATTERNS:
        text = pattern.sub(repl, text)
    return text


def mask_url(url: str) -> str:
    """Redact credentials in a connection URL for safe display."""
    return re.sub(r"(://[^:/@\s]*:)[^@/\s]+(@)", r"\1[REDACTED]\2", url)


def _scrub_patcher(record: Record) -> None:
    """Loguru patcher: scrub the message and any stringly ``extra`` values."""
    record["message"] = scrub(record["message"])
    extra = record["extra"]
    for key, value in list(extra.items()):
        if isinstance(value, str):
            extra[key] = scrub(value)


def configure_logging(settings: Settings) -> None:
    """Install the global logging configuration derived from settings."""
    logger.remove()
    logger.configure(patcher=_scrub_patcher)
    if settings.log_json:
        logger.add(sys.stderr, level=settings.log_level, serialize=True, backtrace=False)
    else:
        logger.add(
            sys.stderr,
            level=settings.log_level,
            colorize=True,
            backtrace=False,
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> "
                "<level>{level: <8}</level> "
                "<cyan>{name}</cyan> - <level>{message}</level>"
            ),
        )
