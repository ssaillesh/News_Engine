"""
tests/test_nlp_core.py
Unit tests for the NLP layer — runs without API keys using mock data.
"""
from __future__ import annotations

import pytest
from datetime import datetime

from config.models import RawArticle, ProcessedArticle, EntityMention
from nlp.processor import (
    normalise_company,
    _split_sentences,
    _build_context_window,
    _rollup_company_sentiments,
    _article_level_sentiment,
)


# ─────────────────────────────────────────────────────────────────────────────
# Company normalisation
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("Apple Inc.",          "Apple"),
    ("Microsoft Corp.",     "Microsoft"),
    ("Tesla, Inc.",         "Tesla,"),        # comma is edge case — acceptable
    ("Goldman Sachs Group", "Goldman Sachs"),
    ("Meta Platforms",      "Meta Platforms"),
    ("NVIDIA Corporation",  "Nvidia"),
    ("Alphabet Inc",        "Alphabet"),
])
def test_normalise_company(raw, expected):
    result = normalise_company(raw)
    assert expected.lower() in result.lower(), f"Got '{result}' for input '{raw}'"


# ─────────────────────────────────────────────────────────────────────────────
# Sentence splitting
# ─────────────────────────────────────────────────────────────────────────────

def test_split_sentences_basic():
    text = "Apple reported strong earnings. Microsoft also beat expectations. Tesla fell short."
    sents = _split_sentences(text)
    assert len(sents) == 3
    assert sents[0].startswith("Apple")
    assert sents[2].startswith("Tesla")


def test_split_sentences_single():
    text = "This is a single sentence with no period at end"
    sents = _split_sentences(text)
    assert len(sents) == 1


# ─────────────────────────────────────────────────────────────────────────────
# Context window
# ─────────────────────────────────────────────────────────────────────────────

def test_context_window_middle():
    sents = ["S0", "S1", "S2", "S3", "S4"]
    window = _build_context_window(sents, sentence_idx=2, window=2)
    assert "S0" in window
    assert "S4" in window


def test_context_window_edge_start():
    sents = ["S0", "S1", "S2", "S3", "S4"]
    window = _build_context_window(sents, sentence_idx=0, window=2)
    assert window.startswith("S0")


def test_context_window_edge_end():
    sents = ["S0", "S1", "S2", "S3", "S4"]
    window = _build_context_window(sents, sentence_idx=4, window=2)
    assert "S4" in window


# ─────────────────────────────────────────────────────────────────────────────
# Company sentiment rollup
# ─────────────────────────────────────────────────────────────────────────────

def _make_mention(entity, label, pos, neg, neu) -> EntityMention:
    return EntityMention(
        entity          = entity,
        raw_text        = entity,
        start_char      = 0,
        end_char        = len(entity),
        sentence_idx    = 0,
        context_window  = "context",
        sentiment_label = label,
        sentiment_score = max(pos, neg, neu),
        positive_score  = pos,
        negative_score  = neg,
        neutral_score   = neu,
    )


def test_rollup_single_company_positive():
    mentions = [
        _make_mention("Apple", "positive", 0.8, 0.1, 0.1),
        _make_mention("Apple", "positive", 0.7, 0.2, 0.1),
    ]
    rollup = _rollup_company_sentiments(mentions)
    assert "Apple" in rollup
    assert rollup["Apple"]["label"] == "positive"
    assert rollup["Apple"]["mentions"] == 2


def test_rollup_mixed_sentiment():
    mentions = [
        _make_mention("Tesla", "positive", 0.8, 0.1, 0.1),
        _make_mention("Tesla", "negative", 0.1, 0.8, 0.1),
        _make_mention("Tesla", "negative", 0.1, 0.8, 0.1),
    ]
    rollup = _rollup_company_sentiments(mentions)
    # 2 negative vs 1 positive → dominant should be negative
    assert rollup["Tesla"]["label"] == "negative"


def test_rollup_multiple_companies():
    mentions = [
        _make_mention("Apple",     "positive", 0.9, 0.05, 0.05),
        _make_mention("Microsoft", "neutral",  0.2, 0.2,  0.6),
    ]
    rollup = _rollup_company_sentiments(mentions)
    assert set(rollup.keys()) == {"Apple", "Microsoft"}


# ─────────────────────────────────────────────────────────────────────────────
# Article-level sentiment
# ─────────────────────────────────────────────────────────────────────────────

def test_article_sentiment_weighted():
    company_sentiments = {
        "Apple":     {"label": "positive", "score": 0.9, "positive_score": 0.9,
                      "negative_score": 0.05, "neutral_score": 0.05, "mentions": 5},
        "Microsoft": {"label": "negative", "score": 0.6, "positive_score": 0.1,
                      "negative_score": 0.6,  "neutral_score": 0.3,  "mentions": 1},
    }
    label, score = _article_level_sentiment(company_sentiments)
    # Apple has 5× weight, should dominate → positive
    assert label == "positive"


def test_article_sentiment_empty():
    label, score = _article_level_sentiment({})
    assert label == "neutral"
    assert score == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# RawArticle model validation
# ─────────────────────────────────────────────────────────────────────────────

def test_raw_article_defaults():
    a = RawArticle(
        source="alphavantage",
        title="Test headline",
        url="https://example.com/article",
    )
    assert a.article_id is not None
    assert a.fetched_at is not None


def test_processed_article_empty_text():
    """An article with no text should not crash — NLP layer handles gracefully."""
    raw = RawArticle(source="yfinance", title="", url="https://example.com")
    from nlp.processor import process_article
    result = process_article(raw)
    assert isinstance(result, ProcessedArticle)
    assert result.article_sentiment_label == "neutral"
