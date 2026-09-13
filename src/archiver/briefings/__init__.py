"""On-demand, AI-written analysis of a single story.

Unlike :mod:`archiver.analysis`, this package reaches the network — Claude reads
the article (via its server-side web fetch) or the document text we already
hold — so it lives apart from the offline enrichment passes. Every analysis is
generated at most once per story and stored.
"""

from archiver.briefings.generator import (
    Briefing,
    BriefingFailed,
    BriefingGenerator,
    BriefingUnavailable,
)
from archiver.briefings.store import get_briefing, get_or_create_briefing

__all__ = [
    "Briefing",
    "BriefingFailed",
    "BriefingGenerator",
    "BriefingUnavailable",
    "get_briefing",
    "get_or_create_briefing",
]
