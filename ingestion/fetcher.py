"""
ingestion/fetcher.py
Pulls news from AlphaVantage, FinnHub, and yfinance.
Merges all three sources and deduplicates by URL + title fingerprint.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone, timedelta
from typing import List, Optional

import httpx
import yfinance as yf
from loguru import logger

from config.models import RawArticle
from config.settings import (
    ALPHA_VANTAGE_API_KEY,
    FINNHUB_API_KEY,
    MAX_ARTICLES_PER_SOURCE,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _normalise_title(title: str) -> str:
    """Lowercase + strip punctuation — used for dedup fingerprinting."""
    return re.sub(r"[^a-z0-9 ]", "", title.lower()).strip()


def _url_key(url: str) -> str:
    return url.strip().rstrip("/").lower()


def _parse_dt(value: Optional[str | int]) -> Optional[datetime]:
    """Best-effort datetime parser across all three API formats."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    # ISO 8601 incl. 'Z' suffix (yfinance pubDate: 2026-07-09T15:30:00Z)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    for fmt in (
        "%Y%m%dT%H%M%S",        # AlphaVantage: 20240501T130000
        "%Y-%m-%dT%H:%M:%S%z",  # ISO 8601
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(str(value)[:19], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Source 1 — AlphaVantage
# ─────────────────────────────────────────────────────────────────────────────

def fetch_alphavantage(tickers: List[str]) -> List[RawArticle]:
    """
    AlphaVantage NEWS_SENTIMENT endpoint.
    Returns up to MAX_ARTICLES_PER_SOURCE articles covering all tickers.
    """
    if not ALPHA_VANTAGE_API_KEY:
        logger.warning("ALPHA_VANTAGE_API_KEY not set — skipping AlphaVantage")
        return []

    articles: List[RawArticle] = []
    ticker_str = ",".join(tickers)

    params = {
        "function": "NEWS_SENTIMENT",
        "tickers":  ticker_str,
        "limit":    MAX_ARTICLES_PER_SOURCE,
        "apikey":   ALPHA_VANTAGE_API_KEY,
    }

    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get("https://www.alphavantage.co/query", params=params)
            resp.raise_for_status()
            data = resp.json()

        feed = data.get("feed", [])
        logger.info(f"AlphaVantage returned {len(feed)} articles for {ticker_str}")

        for item in feed:
            articles.append(RawArticle(
                source       = "alphavantage",
                ticker       = ticker_str,
                title        = item.get("title", ""),
                url          = item.get("url", ""),
                published_at = _parse_dt(item.get("time_published")),
                summary      = item.get("summary", ""),
                full_text    = item.get("summary", ""),
                raw_payload  = item,
            ))
    except Exception as exc:
        logger.error(f"AlphaVantage fetch failed: {exc}")

    return articles


# ─────────────────────────────────────────────────────────────────────────────
# Source 2 — FinnHub
# ─────────────────────────────────────────────────────────────────────────────

def fetch_finnhub(tickers: List[str]) -> List[RawArticle]:
    """
    FinnHub company-news endpoint — last 7 days per ticker.
    """
    if not FINNHUB_API_KEY:
        logger.warning("FINNHUB_API_KEY not set — skipping FinnHub")
        return []

    today    = datetime.utcnow().date()
    week_ago = today - timedelta(days=7)
    articles: List[RawArticle] = []

    for ticker in tickers:
        params = {
            "symbol": ticker,
            "from":   str(week_ago),
            "to":     str(today),
            "token":  FINNHUB_API_KEY,
        }
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.get("https://finnhub.io/api/v1/company-news", params=params)
                resp.raise_for_status()
                items = resp.json()

            items = items[:MAX_ARTICLES_PER_SOURCE]
            logger.info(f"FinnHub returned {len(items)} articles for {ticker}")

            for item in items:
                articles.append(RawArticle(
                    source       = "finnhub",
                    ticker       = ticker,
                    title        = item.get("headline", ""),
                    url          = item.get("url", ""),
                    published_at = _parse_dt(item.get("datetime")),
                    summary      = item.get("summary", ""),
                    full_text    = item.get("summary", ""),
                    raw_payload  = item,
                ))
        except Exception as exc:
            logger.error(f"FinnHub fetch failed for {ticker}: {exc}")

    return articles


# ─────────────────────────────────────────────────────────────────────────────
# Source 3 — yfinance
# ─────────────────────────────────────────────────────────────────────────────

def fetch_yfinance(tickers: List[str]) -> List[RawArticle]:
    """
    yfinance .news property — recent headlines, no API key required.
    """
    articles: List[RawArticle] = []

    for ticker in tickers:
        try:
            tk   = yf.Ticker(ticker)
            news = (tk.news or [])[:MAX_ARTICLES_PER_SOURCE]
            logger.info(f"yfinance returned {len(news)} articles for {ticker}")

            for item in news:
                content  = item.get("content", {})
                title    = item.get("title") or content.get("title", "")
                url      = (
                    item.get("link")
                    or content.get("canonicalUrl", {}).get("url", "")
                    or ""
                )
                pub_raw  = item.get("providerPublishTime") or content.get("pubDate", "")
                summary  = item.get("summary") or content.get("summary", "")

                articles.append(RawArticle(
                    source       = "yfinance",
                    ticker       = ticker,
                    title        = title,
                    url          = url,
                    published_at = _parse_dt(pub_raw),
                    summary      = summary,
                    full_text    = summary,
                    raw_payload  = item,
                ))
        except Exception as exc:
            logger.error(f"yfinance fetch failed for {ticker}: {exc}")

    return articles


# ─────────────────────────────────────────────────────────────────────────────
# Merge + Deduplicate
# ─────────────────────────────────────────────────────────────────────────────

def merge_and_deduplicate(sources: List[List[RawArticle]]) -> List[RawArticle]:
    """
    Combine articles from all sources, remove duplicates in two passes:
      1. Exact URL match
      2. Normalised-title MD5 collision (catches same story from different sources)
    Newest articles win on collision.
    """
    seen_urls:   set[str] = set()
    seen_titles: set[str] = set()
    unique:      List[RawArticle] = []

    all_articles = [a for source in sources for a in source]
    all_articles.sort(
        key=lambda a: a.published_at or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )

    for article in all_articles:
        if not article.title or not article.url:
            continue

        url_key   = _url_key(article.url)
        title_key = hashlib.md5(_normalise_title(article.title).encode()).hexdigest()

        if url_key in seen_urls or title_key in seen_titles:
            continue

        seen_urls.add(url_key)
        seen_titles.add(title_key)
        unique.append(article)

    logger.info(f"Merge: {len(all_articles)} total → {len(unique)} unique after dedup")
    return unique


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def fetch_all(tickers: List[str]) -> List[RawArticle]:
    """Fetch from all three sources, merge, and deduplicate."""
    logger.info(f"Fetching news for tickers: {tickers}")
    return merge_and_deduplicate([
        fetch_alphavantage(tickers),
        fetch_finnhub(tickers),
        fetch_yfinance(tickers),
    ])
