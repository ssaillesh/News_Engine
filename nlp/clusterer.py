"""
nlp/clusterer.py
Event Clustering + Analytics Engine (Layer 3).

Steps:
  1. Pull all article embeddings from FAISS
  2. Run HDBSCAN → cluster labels (-1 = noise)
  3. Per cluster, aggregate entities + sentiments → NewsEvent
  4. Score each event (velocity, novelty, sentiment strength, hot_score)
"""
from __future__ import annotations

import importlib
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Dict, List

import numpy as np
from loguru import logger

from config.models import CompanyEventSentiment, NewsEvent, ProcessedArticle
from config.settings import MIN_CLUSTER_SIZE
from nlp.embedder import get_all_article_vectors, add_event_embedding


# ─────────────────────────────────────────────────────────────────────────────
# Clustering
# ─────────────────────────────────────────────────────────────────────────────

def _run_fallback_clustering(matrix: np.ndarray) -> np.ndarray:
    """Cluster normalized vectors with a cosine-similarity connected-components fallback."""
    if matrix.size == 0:
        return np.empty((0,), dtype=int)

    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    normalized = matrix / norms

    # all-MiniLM-L6-v2 embeddings are already cosine-friendly; 0.70 matches the
    # previous DBSCAN cosine distance threshold of 0.3 reasonably well.
    similarity = normalized @ normalized.T
    adjacency = similarity >= 0.70
    np.fill_diagonal(adjacency, False)

    labels = np.full(matrix.shape[0], -1, dtype=int)
    visited = np.zeros(matrix.shape[0], dtype=bool)
    cluster_id = 0

    for seed in range(matrix.shape[0]):
        if visited[seed]:
            continue

        stack = [seed]
        component = []
        visited[seed] = True

        while stack:
            node = stack.pop()
            component.append(node)

            neighbors = np.where(adjacency[node] & ~visited)[0]
            for neighbor in neighbors:
                visited[neighbor] = True
                stack.append(int(neighbor))

        if len(component) >= MIN_CLUSTER_SIZE:
            labels[np.array(component)] = cluster_id
            cluster_id += 1

    return labels

def _run_clustering(matrix: np.ndarray) -> np.ndarray:
    """Returns integer cluster labels (N,). Label -1 = noise."""
    if matrix.size == 0:
        return np.empty((0,), dtype=int)

    try:
        hdbscan_module = importlib.import_module("hdbscan")
    except ImportError:
        hdbscan_module = None

    if hdbscan_module is not None:
        clusterer = hdbscan_module.HDBSCAN(
            min_cluster_size=MIN_CLUSTER_SIZE,
            min_samples=1,
            metric="euclidean",
            cluster_selection_method="eom",
        )
        labels = clusterer.fit_predict(matrix)
    else:
        try:
            sklearn_cluster = importlib.import_module("sklearn.cluster")
        except ImportError:
            logger.warning("hdbscan and scikit-learn are unavailable; using local clustering fallback")
            labels = _run_fallback_clustering(matrix)
        else:
            labels = sklearn_cluster.DBSCAN(
                eps=0.3, min_samples=MIN_CLUSTER_SIZE, metric="cosine"
            ).fit_predict(matrix)

    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    n_noise    = int((labels == -1).sum())
    logger.info(f"Clustering: {n_clusters} clusters, {n_noise} noise articles")
    return labels


# ─────────────────────────────────────────────────────────────────────────────
# Sentiment aggregation
# ─────────────────────────────────────────────────────────────────────────────

def _aggregate_company_sentiments(
    articles: List[ProcessedArticle],
) -> List[CompanyEventSentiment]:
    """Merge company_sentiments from all articles in one cluster."""
    buckets: Dict[str, dict] = defaultdict(lambda: {
        "pos": 0.0, "neg": 0.0, "neu": 0.0, "mentions": 0
    })

    for art in articles:
        for company, s in art.company_sentiments.items():
            b = buckets[company]
            w = s["mentions"]
            b["pos"]      += s["positive_score"] * w
            b["neg"]      += s["negative_score"] * w
            b["neu"]      += s["neutral_score"]  * w
            b["mentions"] += w

    result = []
    for company, b in buckets.items():
        n = b["mentions"]
        if n == 0:
            continue

        pos = b["pos"] / n
        neg = b["neg"] / n
        neu = b["neu"] / n

        weighted_score = round(pos - neg, 4)

        if pos >= neg and pos >= neu:
            dominant = "positive"
        elif neg >= pos and neg >= neu:
            dominant = "negative"
        else:
            dominant = "neutral"

        result.append(CompanyEventSentiment(
            company        = company,
            mention_count  = n,
            positive_ratio = round(pos, 4),
            negative_ratio = round(neg, 4),
            neutral_ratio  = round(neu, 4),
            weighted_score = weighted_score,
            dominant_label = dominant,
        ))

    result.sort(key=lambda x: x.mention_count, reverse=True)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Hot-topic scoring
# ─────────────────────────────────────────────────────────────────────────────

def _compute_velocity(articles: List[ProcessedArticle]) -> float:
    """Articles per hour over the last 24-hour window."""
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=24)
    recent = [
        a for a in articles
        if a.published_at
        and a.published_at.replace(tzinfo=timezone.utc) >= cutoff
    ]
    return round(len(recent) / 24.0, 4) if recent else 0.0


def _compute_novelty(articles: List[ProcessedArticle]) -> float:
    """1 - (median_age_hours / 168). 168h = 1 week."""
    now  = datetime.now(tz=timezone.utc)
    ages = []
    for a in articles:
        if a.published_at:
            dt = a.published_at if a.published_at.tzinfo else a.published_at.replace(tzinfo=timezone.utc)
            ages.append((now - dt).total_seconds() / 3600)

    if not ages:
        return 0.5
    median_age = sorted(ages)[len(ages) // 2]
    return round(max(0.0, 1 - median_age / 168), 4)


def _compute_hot_score(event: NewsEvent, all_events: List[NewsEvent]) -> float:
    """
    Composite hot score (0–1):
      30% mention_volume  · 25% velocity  · 20% sentiment_strength
      15% source_diversity · 10% novelty
    """
    max_vol = max((e.mention_volume for e in all_events), default=1)
    max_vel = max((e.velocity       for e in all_events), default=1)

    vol_n  = event.mention_volume    / max_vol if max_vol else 0
    vel_n  = event.velocity          / max_vel if max_vel else 0
    sent_n = event.sentiment_strength
    src_n  = len(event.sources) / 3.0
    nov_n  = event.novelty_score

    score = (
        0.30 * vol_n  +
        0.25 * vel_n  +
        0.20 * sent_n +
        0.15 * src_n  +
        0.10 * nov_n
    )
    return round(min(score, 1.0), 4)


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def build_events(articles_by_id: Dict[str, ProcessedArticle]) -> List[NewsEvent]:
    """
    Main entry point.
    articles_by_id: { article_id: ProcessedArticle }
    Returns NewsEvent list sorted by hot_score descending.
    """
    matrix, ref_ids = get_all_article_vectors()

    if matrix.shape[0] < MIN_CLUSTER_SIZE:
        logger.warning(
            f"Only {matrix.shape[0]} embedded articles — "
            f"need at least {MIN_CLUSTER_SIZE} to cluster."
        )
        return []

    labels = _run_clustering(matrix)

    cluster_map: Dict[int, List[str]] = defaultdict(list)
    for ref_id, label in zip(ref_ids, labels):
        if label != -1:
            cluster_map[int(label)].append(ref_id)

    events: List[NewsEvent] = []

    for cluster_id, art_ids in cluster_map.items():
        cluster_articles = [
            articles_by_id[aid] for aid in art_ids if aid in articles_by_id
        ]
        if not cluster_articles:
            continue

        company_sentiments = _aggregate_company_sentiments(cluster_articles)

        cluster_articles.sort(
            key=lambda a: a.published_at or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        rep = cluster_articles[0]

        if company_sentiments:
            strength = sum(
                abs(c.weighted_score) for c in company_sentiments[:5]
            ) / min(5, len(company_sentiments))
        else:
            strength = 0.0

        event = NewsEvent(
            cluster_id            = cluster_id,
            article_ids           = art_ids,
            article_count         = len(art_ids),
            sources               = list({a.source for a in cluster_articles}),
            representative_title  = rep.title,
            representative_url    = rep.url,
            mention_volume        = len(art_ids),
            velocity              = _compute_velocity(cluster_articles),
            novelty_score         = _compute_novelty(cluster_articles),
            sentiment_strength    = round(strength, 4),
            company_sentiments    = company_sentiments,
            top_companies         = [c.company for c in company_sentiments[:5]],
        )
        events.append(event)

    for event in events:
        event.hot_score = _compute_hot_score(event, events)
    events.sort(key=lambda e: e.hot_score, reverse=True)

    logger.info(f"Built {len(events)} events from {len(articles_by_id)} articles")
    return events
