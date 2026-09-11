"""Backfill daily prices for one ticker from Yahoo Finance."""

from __future__ import annotations

import logging

from app.db import sync_session
from app.services.prices import upsert_prices, upsert_security
from app.services.yahoo import YahooError, fetch_daily_prices, fetch_profile
from workers.celery_app import celery_app

log = logging.getLogger(__name__)


@celery_app.task(
    name="prices.backfill_ticker",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(YahooError,),
    retry_backoff=True,
)
def backfill_ticker(self, ticker: str, period: str = "max") -> dict[str, object]:
    """Fetch and store the price history for ``ticker``.

    Retries on Yahoo failures — an unknown symbol and a transient outage look
    the same from here, so give it a few attempts before giving up.

    Returns a summary: ``{"ticker": "AAPL", "bars": 11042, "first": ..., "last": ...}``
    """
    symbol = ticker.upper()
    bars = fetch_daily_prices(symbol, period=period)

    with sync_session() as session:
        upsert_security(session, fetch_profile(symbol))
        written = upsert_prices(session, symbol, bars)

    log.info("backfilled %s: %d bars", symbol, written)
    return {
        "ticker": symbol,
        "bars": written,
        "first": bars[0].date.isoformat(),
        "last": bars[-1].date.isoformat(),
    }
