"""
config/models.py
Pydantic data models shared across every pipeline layer.
These are the canonical schemas — nothing else defines article/entity/event shape.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
import uuid


# ─────────────────────────────────────────────────────────────────────────────
# Layer 1 — Raw Article  (immutable, written once)
# ─────────────────────────────────────────────────────────────────────────────
class RawArticle(BaseModel):
    """Exactly what came off the wire — never mutated after creation."""

    article_id:   str       = Field(default_factory=lambda: str(uuid.uuid4()))
    source:       str                          # "alphavantage" | "finnhub" | "yfinance"
    ticker:       Optional[str]  = None        # query ticker if any
    title:        str
    url:          str
    published_at: Optional[datetime] = None
    fetched_at:   datetime           = Field(default_factory=datetime.utcnow)
    full_text:    Optional[str]  = None
    summary:      Optional[str]  = None
    raw_payload:  Dict[str, Any] = Field(default_factory=dict)  # original API blob


# ─────────────────────────────────────────────────────────────────────────────
# Layer 2 — NLP Processed  (structured intelligence)
# ─────────────────────────────────────────────────────────────────────────────
class EntityMention(BaseModel):
    """One ORG entity extracted by BERT-NER, with its FinBERT sentiment."""

    entity:          str            # normalised company name
    raw_text:        str            # exact span from article
    label:           str = "ORG"
    start_char:      int
    end_char:        int
    sentence_idx:    int            # which sentence in article
    context_window:  str            # ±2 sentences fed to FinBERT
    sentiment_label: str            # "positive" | "negative" | "neutral"
    sentiment_score: float          # confidence 0-1
    positive_score:  float
    negative_score:  float
    neutral_score:   float


class ProcessedArticle(BaseModel):
    """Article after NER + FinBERT — the main working dataset row."""

    article_id:          str
    source:              str
    ticker:              Optional[str]     = None
    title:               str
    url:                 str
    published_at:        Optional[datetime] = None
    processed_at:        datetime           = Field(default_factory=datetime.utcnow)
    sentences:           List[str]          = Field(default_factory=list)
    entities:            List[EntityMention] = Field(default_factory=list)

    # article-level aggregated sentiment (weighted by entity confidence)
    article_sentiment_label: str   = "neutral"
    article_sentiment_score: float = 0.0

    # per-company rollup within this article
    # { "Apple Inc": {"label":"positive","score":0.87,"mentions":3} }
    company_sentiments: Dict[str, Dict[str, Any]] = Field(default_factory=dict)

    embedding_id: Optional[str] = None   # FAISS row reference


# ─────────────────────────────────────────────────────────────────────────────
# Layer 3 — Event + Aggregation  (analytics layer)
# ─────────────────────────────────────────────────────────────────────────────
class CompanyEventSentiment(BaseModel):
    """Aggregated sentiment for one company across all articles in an event."""

    company:         str
    mention_count:   int
    positive_ratio:  float
    negative_ratio:  float
    neutral_ratio:   float
    weighted_score:  float          # -1 (very negative) → +1 (very positive)
    dominant_label:  str


class NewsEvent(BaseModel):
    """
    Cluster of related articles that together describe one 'event'.
    Produced by HDBSCAN over article embeddings.
    """

    event_id:         str = Field(default_factory=lambda: str(uuid.uuid4()))
    cluster_id:       int                           # HDBSCAN label
    created_at:       datetime = Field(default_factory=datetime.utcnow)
    article_ids:      List[str] = Field(default_factory=list)
    article_count:    int       = 0
    sources:          List[str] = Field(default_factory=list)   # unique sources

    # representative headline (closest to cluster centroid)
    representative_title: Optional[str] = None
    representative_url:   Optional[str] = None

    # Hot-topic scores
    mention_volume:   int   = 0
    velocity:         float = 0.0   # articles/hour
    novelty_score:    float = 0.0   # 0–1
    sentiment_strength: float = 0.0 # abs(weighted_score)
    hot_score:        float = 0.0   # composite ranking score

    # Per-company aggregated sentiment across entire event
    company_sentiments: List[CompanyEventSentiment] = Field(default_factory=list)

    # Top companies by mention count
    top_companies: List[str] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Layer 4 — Vector Store metadata  (semantic layer)
# ─────────────────────────────────────────────────────────────────────────────
class EmbeddingRecord(BaseModel):
    """Maps a FAISS row index → what it represents."""

    embedding_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    faiss_index:  int
    kind:         str   # "article" | "sentence" | "event"
    ref_id:       str   # article_id / event_id
    text_preview: str   # first 120 chars for debugging
    created_at:   datetime = Field(default_factory=datetime.utcnow)
