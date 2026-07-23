"""Shared text-handling helpers for the source adapters.

Each source normalizes its own payloads (see ``archiver.sources``); what lives
here is the format-agnostic cleanup they all need — turning publisher HTML into
the plain text stored in ``statuses.content_text``.
"""

from archiver.parsing.text import html_to_text

__all__ = ["html_to_text"]
