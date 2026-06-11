#!/usr/bin/env python3
from __future__ import annotations
# Force PyTorch-only — prevents TF/AVX hang on machines without AVX support
import os
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("USE_TORCH", "1")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

"""
main.py
CLI entry point for the NLP News Intelligence Pipeline.

Usage examples:
  # Batch run for specific tickers
  python main.py batch --tickers AAPL MSFT TSLA NVDA

  # Start the FastAPI server
  python main.py serve

  # Start Redis stream producer (run on cron)
  python main.py produce --tickers AAPL MSFT TSLA

  # Start NLP consumer worker (long-running)
  python main.py consume --worker-name worker-1

  # Query top events from CLI
  python main.py events --limit 10

  # Query company sentiment
  python main.py sentiment --company Apple
"""
import argparse
import json
import sys

from loguru import logger


def _setup_logging(level: str = "INFO") -> None:
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
        level=level,
        colorize=True,
    )
    logger.add(
        "logs/pipeline.log",
        rotation="50 MB",
        retention="7 days",
        level="DEBUG",
    )


def cmd_batch(args) -> None:
    from pipeline.runner import run_batch

    summary = run_batch(
        tickers=args.tickers,
        reuse_stored=not args.force_reprocess,
    )
    print("\n=== Pipeline Summary ===")
    print(json.dumps(summary, indent=2, default=str))


def cmd_serve(args) -> None:
    import uvicorn
    uvicorn.run(
        "pipeline.api:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


def cmd_produce(args) -> None:
    from pipeline.runner import run_producer

    n = run_producer(args.tickers)
    print(f"Published {n} articles to Redis stream.")


def cmd_consume(args) -> None:
    from pipeline.runner import run_consumer_worker

    run_consumer_worker(consumer_name=args.worker_name)



def cmd_events(args) -> None:
    from storage.store import init_db, query_top_events

    init_db()
    events = query_top_events(limit=args.limit)
    if not events:
        print("No events found. Run a batch first.")
        return

    print(f"\n=== Top {len(events)} Events ===")
    for i, evt in enumerate(events, 1):
        companies = json.loads(evt.get("top_companies", "[]"))
        print(
            f"\n{i}. [{evt['hot_score']:.3f}] {evt['representative_title']}\n"
            f"   Articles: {evt['article_count']} | "
            f"Velocity: {evt['velocity']:.2f}/hr | "
            f"Sentiment strength: {evt['sentiment_strength']:.2f}\n"
            f"   Companies: {', '.join(companies[:5])}"
        )


def cmd_sentiment(args) -> None:
    from storage.store import init_db, query_company_sentiment_trend

    init_db()
    rows = query_company_sentiment_trend(args.company, limit=args.limit)
    if not rows:
        print(f"No sentiment data for '{args.company}'")
        return

    print(f"\n=== Sentiment trend for '{args.company}' ({len(rows)} articles) ===")
    pos = sum(1 for r in rows if r["sentiment_label"] == "positive")
    neg = sum(1 for r in rows if r["sentiment_label"] == "negative")
    neu = sum(1 for r in rows if r["sentiment_label"] == "neutral")
    total = len(rows)
    print(f"  Positive: {pos}/{total} ({100*pos/total:.0f}%)")
    print(f"  Negative: {neg}/{total} ({100*neg/total:.0f}%)")
    print(f"  Neutral:  {neu}/{total} ({100*neu/total:.0f}%)")
    print()
    for r in rows[:10]:
        print(f"  [{r['sentiment_label']:8}] {r['title'][:70]}")


# ─────────────────────────────────────────────────────────────────────────────

def main():
    import os
    os.makedirs("logs", exist_ok=True)

    parser = argparse.ArgumentParser(
        description="NLP News Intelligence Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING"])
    sub = parser.add_subparsers(dest="command", required=True)

    # batch
    p_batch = sub.add_parser("batch", help="Run full batch pipeline")
    p_batch.add_argument("--tickers", nargs="+", required=True)
    p_batch.add_argument("--force-reprocess", action="store_true",
                         help="Re-run NLP even on already-processed articles")

    # serve
    p_serve = sub.add_parser("serve", help="Start FastAPI server")
    p_serve.add_argument("--host", default="0.0.0.0")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("--reload", action="store_true")

    # produce
    p_prod = sub.add_parser("produce", help="Push articles to Redis stream")
    p_prod.add_argument("--tickers", nargs="+", required=True)

    # consume
    p_cons = sub.add_parser("consume", help="Start NLP consumer worker")
    p_cons.add_argument("--worker-name", default="worker-1")

    # events
    p_evt = sub.add_parser("events", help="List top events")
    p_evt.add_argument("--limit", type=int, default=10)

    # sentiment
    p_sent = sub.add_parser("sentiment", help="Query company sentiment")
    p_sent.add_argument("--company", required=True)
    p_sent.add_argument("--limit", type=int, default=50)

    args = parser.parse_args()
    _setup_logging(args.log_level)

    dispatch = {
        "batch":     cmd_batch,
        "serve":     cmd_serve,
        "produce":   cmd_produce,
        "consume":   cmd_consume,
        "events":    cmd_events,
        "sentiment": cmd_sentiment,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
