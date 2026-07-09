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

import asyncio
from datetime import datetime, timezone

from config.models import ProcessedArticle
from config.settings import (
    AUTO_REFRESH_ENABLED,
    AUTO_REFRESH_INTERVAL,
    AUTO_REFRESH_TICKERS,
    EVENTS_STORE_DIR,
)
from storage.store import (
    init_db,
    load_processed_article,
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


# Status of the background news refresher — exposed via /refresh/status
_refresh_state: dict = {
    "enabled":      AUTO_REFRESH_ENABLED,
    "interval_sec": AUTO_REFRESH_INTERVAL,
    "tickers":      AUTO_REFRESH_TICKERS,
    "running":      False,
    "last_run_at":  None,
    "last_summary": None,
    "last_error":   None,
}


async def _auto_refresh_loop():
    from pipeline.runner import run_batch   # lazy: heavy NLP imports

    while True:
        _refresh_state["running"] = True
        try:
            summary = await asyncio.to_thread(run_batch, AUTO_REFRESH_TICKERS)
            summary.pop("top_events", None)
            _refresh_state["last_summary"] = summary
            _refresh_state["last_error"] = None
            logger.info(f"Auto-refresh complete: {summary}")
        except Exception as exc:
            _refresh_state["last_error"] = str(exc)
            logger.error(f"Auto-refresh failed: {exc}")
        finally:
            _refresh_state["running"] = False
            _refresh_state["last_run_at"] = datetime.now(timezone.utc).isoformat()
        await asyncio.sleep(AUTO_REFRESH_INTERVAL)


@app.on_event("startup")
async def startup():
    init_db()
    logger.info("API started — PostgreSQL schema ensured")
    if AUTO_REFRESH_ENABLED:
        asyncio.create_task(_auto_refresh_loop())
        logger.info(
            f"Auto-refresh enabled: every {AUTO_REFRESH_INTERVAL}s "
            f"for {AUTO_REFRESH_TICKERS}"
        )


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


@app.get("/news/latest")
def get_latest_story():
    """The single most recent news story, plus refresh metadata."""
    rows = query_latest_articles(limit=1)
    if not rows:
        raise HTTPException(status_code=404, detail="No articles yet — first refresh pending")
    return {"story": rows[0], "refresh": _refresh_state}


@app.get("/refresh/status")
def refresh_status():
    return _refresh_state


@app.get("/stats/sentiment")
def get_sentiment_stats():
    return query_sentiment_stats()


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


# ─────────────────────────────────────────────────────────────────────────────
# Market correlation (sentiment ↔ stock price) — powers the dashboard's
# "Market Correlation" tab. Computed live from the current nlp_processed store +
# yfinance, cached briefly so a browser auto-refresh doesn't hammer Yahoo.
# ─────────────────────────────────────────────────────────────────────────────
import time as _time

_CORR_TTL_SECONDS = 600  # 10 min
_corr_cache: dict = {"key": None, "at": 0.0, "data": None}


@app.get("/analysis/correlation")
def analysis_correlation(
    tickers: str = Query("AAPL,MSFT,TSLA,NVDA", description="Comma-separated symbols"),
    max_lag: int = Query(3, ge=0, le=10),
    refresh: bool = Query(False, description="Bypass the cache and recompute now"),
):
    symbols = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if not symbols:
        raise HTTPException(status_code=400, detail="No tickers given")

    key = (tuple(symbols), max_lag)
    now = _time.time()
    cached = _corr_cache
    if not refresh and cached["key"] == key and (now - cached["at"]) < _CORR_TTL_SECONDS:
        return cached["data"]

    try:
        from analysis.sentiment_stock_correlation import build_payload
        data = build_payload(tickers=symbols, max_lag=max_lag)
    except Exception as exc:  # missing deps, network, etc.
        logger.error(f"correlation build failed: {exc}")
        raise HTTPException(status_code=503, detail=f"Correlation unavailable: {exc}")

    _corr_cache.update(key=key, at=now, data=data)
    return data
