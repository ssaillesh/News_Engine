"""
analysis/ — Sentiment ↔ stock-price correlation layer.

Sits on top of the Layer-2 NLP-processed store (data/nlp_processed/*.json) and
joins it against historical market data pulled live from Yahoo Finance.

Public entry point:
    from analysis.sentiment_stock_correlation import run
    run(tickers=["AAPL", "MSFT", "TSLA", "NVDA"])
"""

from .sentiment_stock_correlation import (
    load_daily_sentiment,
    fetch_stock_data,
    merge_sentiment_price,
    compute_lagged_correlations,
    build_payload,
    run,
)

__all__ = [
    "load_daily_sentiment",
    "fetch_stock_data",
    "merge_sentiment_price",
    "compute_lagged_correlations",
    "build_payload",
    "run",
]
