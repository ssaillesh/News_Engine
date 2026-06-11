"""
storage/store.py
4-Layer Storage Engine — PostgreSQL via SQLAlchemy

Layer 1 — Raw Store          : immutable JSON files + PostgreSQL index
Layer 2 — NLP Processed Store: PostgreSQL rows + JSON sidecars
Layer 3 — Event Store        : PostgreSQL rows + JSON
Layer 4 — Vector Store       : FAISS index + JSON metadata (nlp/embedder.py)

JSON sidecars preserve full fidelity; PostgreSQL rows enable fast queries.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime
from typing import Dict, Generator, List, Optional

from loguru import logger
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool

from config.models import NewsEvent, ProcessedArticle, RawArticle
from config.settings import (
    DATABASE_URL,
    EVENTS_STORE_DIR,
    NLP_STORE_DIR,
    RAW_STORE_DIR,
)


# ─────────────────────────────────────────────────────────────────────────────
# Connection pool (module-level singleton)
# ─────────────────────────────────────────────────────────────────────────────

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(
            DATABASE_URL,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,     # reconnect on stale connections
            poolclass=QueuePool,
        )
    return _engine


@contextmanager
def _db() -> Generator:
    engine = _get_engine()
    with engine.connect() as conn:
        with conn.begin():
            yield conn


# ─────────────────────────────────────────────────────────────────────────────
# Schema initialisation
# ─────────────────────────────────────────────────────────────────────────────

_DDL = [
    # ── Layer 1: Raw articles ─────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS raw_articles (
        article_id   TEXT        PRIMARY KEY,
        source       TEXT        NOT NULL,
        ticker       TEXT,
        title        TEXT        NOT NULL,
        url          TEXT        NOT NULL,
        published_at TIMESTAMPTZ,
        fetched_at   TIMESTAMPTZ NOT NULL,
        json_path    TEXT        NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_raw_source ON raw_articles(source)",
    "CREATE INDEX IF NOT EXISTS idx_raw_ticker ON raw_articles(ticker)",
    "CREATE INDEX IF NOT EXISTS idx_raw_pub    ON raw_articles(published_at)",

    # ── Layer 2a: NLP-processed articles ─────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS processed_articles (
        article_id               TEXT        PRIMARY KEY,
        source                   TEXT        NOT NULL,
        ticker                   TEXT,
        title                    TEXT        NOT NULL,
        url                      TEXT        NOT NULL,
        published_at             TIMESTAMPTZ,
        processed_at             TIMESTAMPTZ NOT NULL,
        article_sentiment_label  TEXT,
        article_sentiment_score  REAL,
        company_count            INTEGER,
        embedding_id             TEXT,
        json_path                TEXT        NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_proc_pub  ON processed_articles(published_at)",
    "CREATE INDEX IF NOT EXISTS idx_proc_sent ON processed_articles(article_sentiment_label)",

    # ── Layer 2b: Per-article company sentiments ──────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS entity_sentiments (
        id               SERIAL  PRIMARY KEY,
        article_id       TEXT    NOT NULL
                            REFERENCES processed_articles(article_id) ON DELETE CASCADE,
        company          TEXT    NOT NULL,
        sentiment_label  TEXT    NOT NULL,
        sentiment_score  REAL,
        positive_score   REAL,
        negative_score   REAL,
        neutral_score    REAL,
        mention_count    INTEGER,
        published_at     TIMESTAMPTZ
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_ent_company ON entity_sentiments(company)",
    "CREATE INDEX IF NOT EXISTS idx_ent_label   ON entity_sentiments(sentiment_label)",

    # ── Layer 3a: Events ──────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS events (
        event_id              TEXT        PRIMARY KEY,
        cluster_id            INTEGER,
        created_at            TIMESTAMPTZ NOT NULL,
        article_count         INTEGER,
        representative_title  TEXT,
        representative_url    TEXT,
        mention_volume        INTEGER,
        velocity              REAL,
        novelty_score         REAL,
        sentiment_strength    REAL,
        hot_score             REAL,
        sources               TEXT,
        top_companies         TEXT,
        json_path             TEXT        NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_evt_hot ON events(hot_score DESC)",

    # ── Layer 3b: Per-event company sentiments ────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS event_company_sentiments (
        id              SERIAL  PRIMARY KEY,
        event_id        TEXT    NOT NULL
                            REFERENCES events(event_id) ON DELETE CASCADE,
        company         TEXT    NOT NULL,
        mention_count   INTEGER,
        positive_ratio  REAL,
        negative_ratio  REAL,
        neutral_ratio   REAL,
        weighted_score  REAL,
        dominant_label  TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_evtc_company ON event_company_sentiments(company)",
]


def init_db() -> None:
    """Create all tables and indexes. Safe to call on every startup."""
    with _db() as conn:
        for stmt in _DDL:
            conn.execute(text(stmt))
    logger.info("PostgreSQL schema initialised.")


# ─────────────────────────────────────────────────────────────────────────────
# Layer 1 — Raw Store
# ─────────────────────────────────────────────────────────────────────────────

def save_raw_article(article: RawArticle) -> None:
    """
    Write article JSON to disk and upsert an index row in PostgreSQL.
    JSON file is immutable — never overwritten on conflict.
    """
    json_path = RAW_STORE_DIR / f"{article.article_id}.json"

    if not json_path.exists():
        json_path.write_text(article.model_dump_json(indent=2))

    with _db() as conn:
        conn.execute(
            text("""
                INSERT INTO raw_articles
                    (article_id, source, ticker, title, url, published_at, fetched_at, json_path)
                VALUES
                    (:article_id, :source, :ticker, :title, :url,
                     :published_at, :fetched_at, :json_path)
                ON CONFLICT (article_id) DO NOTHING
            """),
            {
                "article_id":  article.article_id,
                "source":      article.source,
                "ticker":      article.ticker,
                "title":       article.title,
                "url":         article.url,
                "published_at": article.published_at,
                "fetched_at":  article.fetched_at,
                "json_path":   str(json_path),
            },
        )


def save_raw_batch(articles: List[RawArticle]) -> int:
    saved = 0
    for a in articles:
        save_raw_article(a)
        saved += 1
    logger.info(f"Raw store: {saved} articles written")
    return saved


def load_raw_article(article_id: str) -> Optional[RawArticle]:
    json_path = RAW_STORE_DIR / f"{article_id}.json"
    if not json_path.exists():
        return None
    return RawArticle(**json.loads(json_path.read_text()))


# ─────────────────────────────────────────────────────────────────────────────
# Layer 2 — NLP Processed Store
# ─────────────────────────────────────────────────────────────────────────────

def save_processed_article(article: ProcessedArticle) -> None:
    json_path = NLP_STORE_DIR / f"{article.article_id}.json"
    json_path.write_text(article.model_dump_json(indent=2))

    with _db() as conn:
        conn.execute(
            text("""
                INSERT INTO processed_articles
                    (article_id, source, ticker, title, url, published_at,
                     processed_at, article_sentiment_label, article_sentiment_score,
                     company_count, embedding_id, json_path)
                VALUES
                    (:article_id, :source, :ticker, :title, :url, :published_at,
                     :processed_at, :sentiment_label, :sentiment_score,
                     :company_count, :embedding_id, :json_path)
                ON CONFLICT (article_id) DO UPDATE SET
                    article_sentiment_label = EXCLUDED.article_sentiment_label,
                    article_sentiment_score = EXCLUDED.article_sentiment_score,
                    company_count           = EXCLUDED.company_count,
                    embedding_id            = EXCLUDED.embedding_id,
                    json_path               = EXCLUDED.json_path
            """),
            {
                "article_id":      article.article_id,
                "source":          article.source,
                "ticker":          article.ticker,
                "title":           article.title,
                "url":             article.url,
                "published_at":    article.published_at,
                "processed_at":    article.processed_at,
                "sentiment_label": article.article_sentiment_label,
                "sentiment_score": article.article_sentiment_score,
                "company_count":   len(article.company_sentiments),
                "embedding_id":    article.embedding_id,
                "json_path":       str(json_path),
            },
        )

        # Replace entity sentiments for this article
        conn.execute(
            text("DELETE FROM entity_sentiments WHERE article_id = :aid"),
            {"aid": article.article_id},
        )
        for company, s in article.company_sentiments.items():
            conn.execute(
                text("""
                    INSERT INTO entity_sentiments
                        (article_id, company, sentiment_label, sentiment_score,
                         positive_score, negative_score, neutral_score,
                         mention_count, published_at)
                    VALUES
                        (:article_id, :company, :label, :score,
                         :pos, :neg, :neu, :mentions, :published_at)
                """),
                {
                    "article_id":  article.article_id,
                    "company":     company,
                    "label":       s["label"],
                    "score":       s["score"],
                    "pos":         s["positive_score"],
                    "neg":         s["negative_score"],
                    "neu":         s["neutral_score"],
                    "mentions":    s["mentions"],
                    "published_at": article.published_at,
                },
            )


def save_processed_batch(articles: List[ProcessedArticle]) -> int:
    for a in articles:
        save_processed_article(a)
    logger.info(f"NLP store: {len(articles)} processed articles saved")
    return len(articles)


def load_processed_article(article_id: str) -> Optional[ProcessedArticle]:
    json_path = NLP_STORE_DIR / f"{article_id}.json"
    if not json_path.exists():
        return None
    return ProcessedArticle(**json.loads(json_path.read_text()))


def load_all_processed() -> Dict[str, ProcessedArticle]:
    """Load all processed articles into memory. Used by clustering."""
    result = {}
    for p in NLP_STORE_DIR.glob("*.json"):
        try:
            a = ProcessedArticle(**json.loads(p.read_text()))
            result[a.article_id] = a
        except Exception as exc:
            logger.warning(f"Could not load {p}: {exc}")
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Layer 3 — Event Store
# ─────────────────────────────────────────────────────────────────────────────

def save_event(event: NewsEvent) -> None:
    json_path = EVENTS_STORE_DIR / f"{event.event_id}.json"
    json_path.write_text(event.model_dump_json(indent=2))

    with _db() as conn:
        conn.execute(
            text("""
                INSERT INTO events
                    (event_id, cluster_id, created_at, article_count,
                     representative_title, representative_url,
                     mention_volume, velocity, novelty_score,
                     sentiment_strength, hot_score,
                     sources, top_companies, json_path)
                VALUES
                    (:event_id, :cluster_id, :created_at, :article_count,
                     :rep_title, :rep_url,
                     :mention_volume, :velocity, :novelty_score,
                     :sentiment_strength, :hot_score,
                     :sources, :top_companies, :json_path)
                ON CONFLICT (event_id) DO UPDATE SET
                    article_count       = EXCLUDED.article_count,
                    mention_volume      = EXCLUDED.mention_volume,
                    velocity            = EXCLUDED.velocity,
                    novelty_score       = EXCLUDED.novelty_score,
                    sentiment_strength  = EXCLUDED.sentiment_strength,
                    hot_score           = EXCLUDED.hot_score,
                    sources             = EXCLUDED.sources,
                    top_companies       = EXCLUDED.top_companies,
                    json_path           = EXCLUDED.json_path
            """),
            {
                "event_id":          event.event_id,
                "cluster_id":        event.cluster_id,
                "created_at":        event.created_at,
                "article_count":     event.article_count,
                "rep_title":         event.representative_title,
                "rep_url":           event.representative_url,
                "mention_volume":    event.mention_volume,
                "velocity":          event.velocity,
                "novelty_score":     event.novelty_score,
                "sentiment_strength": event.sentiment_strength,
                "hot_score":         event.hot_score,
                "sources":           json.dumps(event.sources),
                "top_companies":     json.dumps(event.top_companies),
                "json_path":         str(json_path),
            },
        )

        conn.execute(
            text("DELETE FROM event_company_sentiments WHERE event_id = :eid"),
            {"eid": event.event_id},
        )
        for cs in event.company_sentiments:
            conn.execute(
                text("""
                    INSERT INTO event_company_sentiments
                        (event_id, company, mention_count,
                         positive_ratio, negative_ratio, neutral_ratio,
                         weighted_score, dominant_label)
                    VALUES
                        (:event_id, :company, :mention_count,
                         :pos, :neg, :neu, :weighted_score, :dominant_label)
                """),
                {
                    "event_id":      event.event_id,
                    "company":       cs.company,
                    "mention_count": cs.mention_count,
                    "pos":           cs.positive_ratio,
                    "neg":           cs.negative_ratio,
                    "neu":           cs.neutral_ratio,
                    "weighted_score": cs.weighted_score,
                    "dominant_label": cs.dominant_label,
                },
            )


def save_events_batch(events: List[NewsEvent]) -> int:
    for e in events:
        save_event(e)
    logger.info(f"Event store: {len(events)} events saved")
    return len(events)


# ─────────────────────────────────────────────────────────────────────────────
# Query helpers
# ─────────────────────────────────────────────────────────────────────────────

def query_top_events(limit: int = 20, since_days: Optional[int] = None) -> List[dict]:
    """Return top N events by hot_score, optionally restricted to the last N days."""
    with _db() as conn:
        if since_days:
            rows = conn.execute(
                text(f"SELECT * FROM events WHERE created_at >= NOW() - INTERVAL '{int(since_days)} days' ORDER BY hot_score DESC LIMIT :limit"),
                {"limit": limit},
            ).mappings().all()
        else:
            rows = conn.execute(
                text("SELECT * FROM events ORDER BY hot_score DESC LIMIT :limit"),
                {"limit": limit},
            ).mappings().all()
    return [dict(r) for r in rows]


def query_company_sentiment_trend(company: str, limit: int = 50) -> List[dict]:
    """Recent sentiment rows for a company name across articles (partial match)."""
    with _db() as conn:
        rows = conn.execute(
            text("""
                SELECT es.*, pa.title, pa.source
                FROM   entity_sentiments   es
                JOIN   processed_articles  pa ON es.article_id = pa.article_id
                WHERE  es.company ILIKE :company
                ORDER  BY es.published_at DESC
                LIMIT  :limit
            """),
            {"company": f"%{company}%", "limit": limit},
        ).mappings().all()
    return [dict(r) for r in rows]


def query_latest_articles(limit: int = 50) -> List[dict]:
    """Latest processed articles with sentiment, newest first."""
    with _db() as conn:
        rows = conn.execute(
            text("""
                SELECT article_id, title, source, ticker, url,
                       article_sentiment_label, article_sentiment_score,
                       published_at, processed_at
                FROM   processed_articles
                ORDER  BY COALESCE(published_at, processed_at) DESC NULLS LAST
                LIMIT  :limit
            """),
            {"limit": limit},
        ).mappings().all()
    return [dict(r) for r in rows]


def query_sentiment_stats() -> dict:
    """Aggregate positive/negative/neutral counts across all processed articles."""
    with _db() as conn:
        row = conn.execute(
            text("""
                SELECT
                    COUNT(*) FILTER (WHERE article_sentiment_label = 'positive') AS positive,
                    COUNT(*) FILTER (WHERE article_sentiment_label = 'negative') AS negative,
                    COUNT(*) FILTER (WHERE article_sentiment_label = 'neutral')  AS neutral,
                    COUNT(*) AS total
                FROM processed_articles
            """)
        ).mappings().one()
    return dict(row)


def query_company_leaderboard(limit: int = 25) -> dict:
    """
    Companies AND people ranked by mention count, with FinBERT sentiment scores,
    velocity (articles/hr in last 24h), and top positive/negative article links.
    Returns {"companies": [...], "people": [...]}.
    """
    from nlp.normalise import classify

    with _db() as conn:
        rows = conn.execute(
            text("""
                SELECT
                    company,
                    SUM(mention_count)         AS total_mentions,
                    COUNT(DISTINCT article_id) AS article_count,
                    AVG(positive_score)        AS avg_positive,
                    AVG(negative_score)        AS avg_negative,
                    AVG(neutral_score)         AS avg_neutral
                FROM   entity_sentiments
                GROUP  BY company
            """)
        ).mappings().all()

        # Articles per company processed in the last 24h → velocity
        vel_rows = conn.execute(
            text("""
                SELECT es.company, COUNT(DISTINCT es.article_id) AS recent_count
                FROM   entity_sentiments es
                JOIN   processed_articles pa ON es.article_id = pa.article_id
                WHERE  pa.processed_at >= NOW() - INTERVAL '24 hours'
                GROUP  BY es.company
            """)
        ).mappings().all()
        velocity_map = {r["company"]: int(r["recent_count"]) for r in vel_rows}

        # Best positive article per raw company name
        top_pos_rows = conn.execute(
            text("""
                SELECT DISTINCT ON (es.company)
                       es.company, pa.title, pa.url, pa.article_sentiment_score
                FROM   entity_sentiments es
                JOIN   processed_articles pa ON es.article_id = pa.article_id
                WHERE  pa.article_sentiment_label = 'positive'
                ORDER  BY es.company, pa.article_sentiment_score DESC NULLS LAST
            """)
        ).mappings().all()
        top_pos_map = {r["company"]: {"title": r["title"], "url": r["url"]} for r in top_pos_rows}

        # Best negative article per raw company name
        top_neg_rows = conn.execute(
            text("""
                SELECT DISTINCT ON (es.company)
                       es.company, pa.title, pa.url, pa.article_sentiment_score
                FROM   entity_sentiments es
                JOIN   processed_articles pa ON es.article_id = pa.article_id
                WHERE  pa.article_sentiment_label = 'negative'
                ORDER  BY es.company, pa.article_sentiment_score DESC NULLS LAST
            """)
        ).mappings().all()
        top_neg_map = {r["company"]: {"title": r["title"], "url": r["url"]} for r in top_neg_rows}

    # Merge into buckets keyed by canonical name + type
    buckets: dict[tuple[str, str], dict] = {}
    for r in rows:
        canonical, etype = classify(r["company"])
        if etype == "noise":
            continue
        key = (canonical, etype)
        if key not in buckets:
            buckets[key] = {
                "name":            canonical,
                "type":            etype,
                "total_mentions":  0,
                "article_count":   0,
                "_pos":            [],
                "_neg":            [],
                "_neu":            [],
                "_vel_count":      0,
                "_top_pos":        None,
                "_top_neg":        None,
            }
        b = buckets[key]
        b["total_mentions"] += int(r["total_mentions"] or 0)
        b["article_count"]  += int(r["article_count"]  or 0)
        b["_pos"].append(float(r["avg_positive"] or 0))
        b["_neg"].append(float(r["avg_negative"] or 0))
        b["_neu"].append(float(r["avg_neutral"]  or 0))
        b["_vel_count"] += velocity_map.get(r["company"], 0)
        if b["_top_pos"] is None and r["company"] in top_pos_map:
            b["_top_pos"] = top_pos_map[r["company"]]
        if b["_top_neg"] is None and r["company"] in top_neg_map:
            b["_top_neg"] = top_neg_map[r["company"]]

    companies, people = [], []
    for b in buckets.values():
        pos = sum(b["_pos"]) / len(b["_pos"])
        neg = sum(b["_neg"]) / len(b["_neg"])
        neu = sum(b["_neu"]) / len(b["_neu"])
        dominant = (
            "positive" if pos >= neg and pos >= neu else
            "negative" if neg >= pos and neg >= neu else
            "neutral"
        )
        entry = {
            "company":        b["name"],
            "total_mentions": b["total_mentions"],
            "article_count":  b["article_count"],
            "avg_positive":   round(pos, 3),
            "avg_negative":   round(neg, 3),
            "avg_neutral":    round(neu, 3),
            "dominant_label": dominant,
            "velocity_24h":   round(b["_vel_count"] / 24.0, 2),
            "top_positive":   b["_top_pos"],
            "top_negative":   b["_top_neg"],
        }
        (companies if b["type"] == "company" else people).append(entry)

    companies.sort(key=lambda x: x["total_mentions"], reverse=True)
    people.sort(   key=lambda x: x["total_mentions"], reverse=True)
    return {"companies": companies[:limit], "people": people}


def search_events_and_articles(query: str, limit: int = 20) -> dict:
    """Search events and articles by title, company name, or ticker."""
    pattern = f"%{query}%"
    with _db() as conn:
        events = conn.execute(
            text("""
                SELECT * FROM events
                WHERE  representative_title ILIKE :q
                    OR top_companies        ILIKE :q
                ORDER  BY hot_score DESC
                LIMIT  :limit
            """),
            {"q": pattern, "limit": limit},
        ).mappings().all()

        articles = conn.execute(
            text("""
                SELECT pa.article_id, pa.title, pa.source, pa.ticker,
                       pa.article_sentiment_label, pa.article_sentiment_score,
                       pa.published_at, pa.url
                FROM   processed_articles pa
                WHERE  pa.title  ILIKE :q
                    OR pa.ticker ILIKE :q
                ORDER  BY pa.published_at DESC NULLS LAST
                LIMIT  :limit
            """),
            {"q": pattern, "limit": limit},
        ).mappings().all()

    return {
        "query":    query,
        "events":   [dict(r) for r in events],
        "articles": [dict(r) for r in articles],
    }
