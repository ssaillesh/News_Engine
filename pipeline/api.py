"""
pipeline/api.py
FastAPI layer — serves NLP pipeline results.

Endpoints:
  POST /run/batch                   — trigger a full batch pipeline run
  GET  /events                      — top hot events
  GET  /events/{event_id}           — single event detail
  GET  /company/{name}/sentiment    — company sentiment trend
  GET  /articles/{article_id}       — processed article detail
  GET  /health                      — liveness check
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from pydantic import BaseModel

from config.models import ProcessedArticle
from config.settings import EVENTS_STORE_DIR
from storage.store import (
    init_db,
    load_processed_article,
    query_company_leaderboard,
    query_company_sentiment_trend,
    query_latest_articles,
    query_sentiment_stats,
    query_top_events,
    search_events_and_articles,
)

_STATIC_DIR = Path(__file__).parent.parent / "static"


# ─────────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="NLP News Intelligence Pipeline",
    description="NER + FinBERT entity-level sentiment on financial news",
    version="1.0.0",
)


app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.on_event("startup")
async def startup():
    init_db()
    logger.info("API started — PostgreSQL schema ensured")


@app.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(str(_STATIC_DIR / "index.html"))


# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────

class BatchRunRequest(BaseModel):
    tickers:      List[str]
    reuse_stored: bool = True


class BatchRunResponse(BaseModel):
    tickers:           List[str]
    raw_fetched:       int
    new_nlp_processed: int
    total_in_store:    int
    events_built:      int
    top_events:        list


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/run/batch", response_model=BatchRunResponse)
def trigger_batch(req: BatchRunRequest):
    from pipeline.runner import run_batch   # lazy: keeps startup fast
    try:
        summary = run_batch(req.tickers, reuse_stored=req.reuse_stored)
        return BatchRunResponse(**summary)
    except Exception as exc:
        logger.error(f"Batch run failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/events")
def get_top_events(
    limit: int = Query(20, ge=1, le=100),
    since_days: int = Query(None, ge=1, le=90),
):
    return query_top_events(limit=limit, since_days=since_days)


@app.get("/events/{event_id}")
def get_event(event_id: str):
    json_path = EVENTS_STORE_DIR / f"{event_id}.json"
    if not json_path.exists():
        raise HTTPException(status_code=404, detail="Event not found")
    return json.loads(json_path.read_text())


@app.get("/company/{name}/sentiment")
def get_company_sentiment(
    name: str,
    limit: int = Query(50, ge=1, le=200),
):
    rows = query_company_sentiment_trend(name, limit=limit)
    if not rows:
        raise HTTPException(status_code=404, detail=f"No sentiment data for '{name}'")
    return {"company": name, "data_points": len(rows), "trend": rows}


@app.get("/news")
def get_news(limit: int = Query(100, ge=1, le=200)):
    return query_latest_articles(limit=limit)


@app.get("/stats/sentiment")
def get_sentiment_stats():
    return query_sentiment_stats()


@app.get("/companies/leaderboard")
def get_company_leaderboard(limit: int = Query(25, ge=1, le=50)):
    # Returns {"companies": [...], "people": [...]}
    return query_company_leaderboard(limit=limit)


@app.get("/search")
def search(
    q: str = Query(..., min_length=1, description="Keyword, company name, or ticker"),
    limit: int = Query(20, ge=1, le=50),
):
    return search_events_and_articles(q, limit=limit)


@app.get("/articles/{article_id}")
def get_article(article_id: str):
    article = load_processed_article(article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return article
