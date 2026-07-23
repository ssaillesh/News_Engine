"""Offline enrichment passes over already-archived content.

Analysis never fetches anything and never mutates the captured record — it reads
stored statuses and writes derived rows alongside them. That keeps every pass
re-runnable: drop the derived table, run the pass again, get the same answer.
"""

from archiver.analysis.pipeline import (
    DEFAULT_SOURCES,
    ScoreReport,
    SummaryReport,
    score_statuses,
    summarize_statuses,
)
from archiver.analysis.sentiment import (
    FINBERT_MODEL,
    LABELS,
    FinBertScorer,
    ModelUnavailableError,
    SentimentReading,
)
from archiver.analysis.summarize import SUMMARY_MODEL, Summarizer

__all__ = [
    "DEFAULT_SOURCES",
    "FINBERT_MODEL",
    "LABELS",
    "SUMMARY_MODEL",
    "FinBertScorer",
    "ModelUnavailableError",
    "ScoreReport",
    "SentimentReading",
    "SummaryReport",
    "Summarizer",
    "score_statuses",
    "summarize_statuses",
]
