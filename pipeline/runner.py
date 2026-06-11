"""
pipeline/runner.py
Pipeline orchestrator — wires all layers together.

Two execution modes:
  run_batch(tickers)      : fetch → NLP → embed → cluster → store  (cron-friendly)
  run_producer(tickers)   : fetch → publish to Redis stream
  run_consumer_worker()   : long-running Redis consumer → NLP → store
"""
from __future__ import annotations

from typing import List

from loguru import logger

from config.models import RawArticle, ProcessedArticle
from ingestion.fetcher import fetch_all
from nlp.processor import process_batch
from nlp.embedder import add_article_embeddings
from nlp.clusterer import build_events
from storage.store import (
    init_db,
    save_raw_batch,
    save_processed_batch,
    save_events_batch,
    load_all_processed,
    query_top_events,
)


# ─────────────────────────────────────────────────────────────────────────────
# Batch mode
# ─────────────────────────────────────────────────────────────────────────────

def run_batch(tickers: List[str], reuse_stored: bool = True) -> dict:
    """
    Full pipeline run for a list of tickers.

    Steps:
      1. Ingest from AlphaVantage + FinnHub + yfinance
      2. Save raw articles (Layer 1)
      3. NLP — NER + FinBERT (skip already-processed if reuse_stored)
      4. Embed — SBERT → FAISS (Layer 4)
      5. Cluster — HDBSCAN → events (Layer 3)
      6. Return summary dict
    """
    logger.info(f"=== Batch pipeline start | tickers={tickers} ===")
    init_db()

    # Step 1+2 — Ingest
    raw_articles: List[RawArticle] = fetch_all(tickers)
    save_raw_batch(raw_articles)
    logger.info(f"Step 1 complete: {len(raw_articles)} raw articles")

    # Step 3 — NLP
    if reuse_stored:
        already_processed = load_all_processed()
        to_process = [a for a in raw_articles if a.article_id not in already_processed]
        logger.info(
            f"Step 2 filter: {len(to_process)} new articles to process "
            f"({len(already_processed)} already in NLP store)"
        )
    else:
        to_process        = raw_articles
        already_processed = {}

    new_processed: List[ProcessedArticle] = []
    if to_process:
        new_processed = process_batch(to_process)
        save_processed_batch(new_processed)
        logger.info(f"Step 3 complete: {len(new_processed)} articles NLP-processed")

    # Step 4 — Embed
    if new_processed:
        new_processed = add_article_embeddings(new_processed)
        save_processed_batch(new_processed)   # re-save with embedding_id populated
        logger.info(f"Step 4 complete: embeddings stored for {len(new_processed)} articles")

    # Step 5 — Cluster
    all_processed = {**already_processed, **{a.article_id: a for a in new_processed}}
    events = []
    if len(all_processed) >= 3:
        events = build_events(all_processed)
        save_events_batch(events)
        logger.info(f"Step 5 complete: {len(events)} events built")
    else:
        logger.warning("Not enough articles for clustering — skipping event layer")

    summary = {
        "tickers":           tickers,
        "raw_fetched":       len(raw_articles),
        "new_nlp_processed": len(new_processed),
        "total_in_store":    len(all_processed),
        "events_built":      len(events),
        "top_events":        query_top_events(limit=5),
    }

    logger.info(f"=== Batch pipeline complete | {summary} ===")
    return summary


# ─────────────────────────────────────────────────────────────────────────────
# Streaming mode — producer side
# ─────────────────────────────────────────────────────────────────────────────

def run_producer(tickers: List[str]) -> int:
    """Fetch articles and push to Redis stream. Run on a cron schedule."""
    from ingestion.redis_queue import publish_articles

    init_db()
    raw_articles = fetch_all(tickers)
    save_raw_batch(raw_articles)
    n = publish_articles(raw_articles)
    logger.info(f"Producer: published {n} articles to Redis stream")
    return n


# ─────────────────────────────────────────────────────────────────────────────
# Streaming mode — consumer side
# ─────────────────────────────────────────────────────────────────────────────

def run_consumer_worker(consumer_name: str = "worker-1") -> None:
    """
    Long-running NLP consumer worker.
    Reads from Redis stream, processes each article, saves to storage.
    Triggers re-clustering every 50 new articles.
    """
    from ingestion.redis_queue import consume_articles, ack_article

    init_db()
    processed_count = 0
    logger.info(f"Consumer worker '{consumer_name}' started")

    for msg_id, raw in consume_articles(consumer_name=consumer_name):
        try:
            processed = process_batch([raw])
            if processed:
                embedded = add_article_embeddings(processed)
                save_processed_batch(embedded)
                processed_count += 1
                logger.debug(f"Processed {raw.article_id} | count={processed_count}")

            if processed_count % 50 == 0 and processed_count > 0:
                logger.info("Triggering re-clustering after 50 new articles")
                all_processed = load_all_processed()
                events        = build_events(all_processed)
                save_events_batch(events)

        except Exception as exc:
            logger.error(f"Worker error on {msg_id}: {exc}")
        finally:
            ack_article(None, msg_id)
