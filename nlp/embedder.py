"""
nlp/embedder.py
Embedding + Vector Store layer (Layer 4).

Responsibilities:
  - Generate SBERT embeddings for articles and events
  - Store / retrieve via FAISS (local, persisted to disk)
  - Maintain a JSON metadata sidecar: FAISS index position → EmbeddingRecord
  - Cosine-similarity search for deduplication and clustering input
"""
from __future__ import annotations

import json
from typing import List, Optional, Tuple

import faiss
import numpy as np
from loguru import logger
from sentence_transformers import SentenceTransformer

from config.models import EmbeddingRecord, ProcessedArticle, NewsEvent
from config.settings import EMBEDDING_MODEL, VECTOR_STORE_DIR


# ─────────────────────────────────────────────────────────────────────────────
# Paths + constants
# ─────────────────────────────────────────────────────────────────────────────

_FAISS_INDEX_PATH = VECTOR_STORE_DIR / "articles.faiss"
_META_PATH        = VECTOR_STORE_DIR / "embedding_meta.json"
_EMBEDDING_DIM    = 384   # all-MiniLM-L6-v2 output dimension


# ─────────────────────────────────────────────────────────────────────────────
# Model singleton
# ─────────────────────────────────────────────────────────────────────────────

_encoder: Optional[SentenceTransformer] = None


def _get_encoder() -> SentenceTransformer:
    global _encoder
    if _encoder is None:
        logger.info(f"Loading embedding model: {EMBEDDING_MODEL}")
        _encoder = SentenceTransformer(EMBEDDING_MODEL)
    return _encoder


# ─────────────────────────────────────────────────────────────────────────────
# FAISS index management
# ─────────────────────────────────────────────────────────────────────────────

def _load_or_create_index() -> faiss.IndexFlatIP:
    """
    IndexFlatIP = inner product, equivalent to cosine similarity on L2-normalised vectors.
    """
    if _FAISS_INDEX_PATH.exists():
        index = faiss.read_index(str(_FAISS_INDEX_PATH))
        logger.debug(f"FAISS index loaded ({index.ntotal} vectors)")
    else:
        index = faiss.IndexFlatIP(_EMBEDDING_DIM)
        logger.debug("FAISS index created (empty)")
    return index


def _save_index(index: faiss.IndexFlatIP) -> None:
    faiss.write_index(index, str(_FAISS_INDEX_PATH))


def _load_meta() -> List[dict]:
    if _META_PATH.exists():
        return json.loads(_META_PATH.read_text())
    return []


def _save_meta(meta: List[dict]) -> None:
    _META_PATH.write_text(json.dumps(meta, default=str, indent=2))


# ─────────────────────────────────────────────────────────────────────────────
# Core encode
# ─────────────────────────────────────────────────────────────────────────────

def encode(texts: List[str]) -> np.ndarray:
    """
    Encode strings → L2-normalised float32 matrix (N × dim).
    L2 normalisation enables cosine similarity via inner product.
    """
    vecs = _get_encoder().encode(texts, convert_to_numpy=True, show_progress_bar=False)
    vecs = vecs.astype(np.float32)
    faiss.normalize_L2(vecs)
    return vecs


# ─────────────────────────────────────────────────────────────────────────────
# Add embeddings
# ─────────────────────────────────────────────────────────────────────────────

def add_article_embeddings(articles: List[ProcessedArticle]) -> List[ProcessedArticle]:
    """
    Embed each article (title + first 3 sentences), store in FAISS,
    attach embedding_id to the ProcessedArticle. Returns the updated list.
    """
    if not articles:
        return articles

    index = _load_or_create_index()
    meta  = _load_meta()

    texts     = [" ".join([a.title] + a.sentences[:3]) for a in articles]
    vecs      = encode(texts)
    start_idx = index.ntotal
    index.add(vecs)

    for i, article in enumerate(articles):
        rec = EmbeddingRecord(
            faiss_index  = start_idx + i,
            kind         = "article",
            ref_id       = article.article_id,
            text_preview = texts[i][:120],
        )
        meta.append(rec.model_dump())
        article.embedding_id = rec.embedding_id

    _save_index(index)
    _save_meta(meta)

    logger.info(f"Added {len(articles)} article embeddings. Index size: {index.ntotal}")
    return articles


def add_event_embedding(event: NewsEvent, representative_text: str) -> str:
    """Embed a NewsEvent centroid text. Returns embedding_id."""
    index = _load_or_create_index()
    meta  = _load_meta()

    vec       = encode([representative_text])
    start_idx = index.ntotal
    index.add(vec)

    rec = EmbeddingRecord(
        faiss_index  = start_idx,
        kind         = "event",
        ref_id       = event.event_id,
        text_preview = representative_text[:120],
    )
    meta.append(rec.model_dump())

    _save_index(index)
    _save_meta(meta)

    return rec.embedding_id


# ─────────────────────────────────────────────────────────────────────────────
# Similarity search
# ─────────────────────────────────────────────────────────────────────────────

def search_similar(
    query_text: str,
    top_k: int = 10,
    kind_filter: Optional[str] = None,
) -> List[Tuple[str, float]]:
    """
    Return list of (ref_id, cosine_score) for the top-k most similar stored vectors.
    kind_filter: "article" | "sentence" | "event" (None = all).
    """
    index = _load_or_create_index()
    meta  = _load_meta()

    if index.ntotal == 0:
        return []

    vec = encode([query_text])
    scores, indices = index.search(vec, min(top_k * 3, index.ntotal))

    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0 or idx >= len(meta):
            continue
        record = meta[idx]
        if kind_filter and record.get("kind") != kind_filter:
            continue
        results.append((record["ref_id"], float(score)))
        if len(results) >= top_k:
            break

    return results


def get_all_article_vectors() -> Tuple[np.ndarray, List[str]]:
    """
    Return (embedding_matrix, article_ids) for all article-kind embeddings.
    Used by the clustering layer.
    """
    index = _load_or_create_index()
    meta  = _load_meta()

    article_meta = [(i, m) for i, m in enumerate(meta) if m.get("kind") == "article"]
    if not article_meta:
        return np.empty((0, _EMBEDDING_DIM), dtype=np.float32), []

    faiss_indices = [m["faiss_index"] for _, m in article_meta]
    ref_ids       = [m["ref_id"]      for _, m in article_meta]

    matrix = np.vstack([
        index.reconstruct(fi).reshape(1, -1)
        for fi in faiss_indices
    ])

    return matrix.astype(np.float32), ref_ids
