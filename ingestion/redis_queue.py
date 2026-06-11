"""
ingestion/redis_queue.py
Redis Streams — queue layer between ingestion and NLP workers.

Producer  : push RawArticle JSON onto the stream
Consumer  : read and yield RawArticle objects for the NLP layer
"""
from __future__ import annotations

import json
import time
from typing import Generator, Optional

import redis
from loguru import logger

from config.models import RawArticle
from config.settings import (
    REDIS_HOST,
    REDIS_PORT,
    REDIS_DB,
    REDIS_STREAM_NAME,
    REDIS_CONSUMER_GROUP,
)


# ─────────────────────────────────────────────────────────────────────────────
# Connection
# ─────────────────────────────────────────────────────────────────────────────

def get_redis() -> redis.Redis:
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        decode_responses=True,
    )


def ensure_consumer_group(r: redis.Redis) -> None:
    """Create the consumer group if it doesn't already exist."""
    try:
        r.xgroup_create(
            name=REDIS_STREAM_NAME,
            groupname=REDIS_CONSUMER_GROUP,
            id="0",
            mkstream=True,
        )
        logger.info(f"Consumer group '{REDIS_CONSUMER_GROUP}' created.")
    except redis.exceptions.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise


# ─────────────────────────────────────────────────────────────────────────────
# Producer
# ─────────────────────────────────────────────────────────────────────────────

def publish_articles(articles: list[RawArticle]) -> int:
    """Push each RawArticle onto the Redis stream. Returns count published."""
    if not articles:
        return 0

    r = get_redis()
    ensure_consumer_group(r)

    count = 0
    for article in articles:
        r.xadd(REDIS_STREAM_NAME, {"payload": article.model_dump_json()})
        count += 1

    logger.info(f"Published {count} articles to stream '{REDIS_STREAM_NAME}'")
    return count


# ─────────────────────────────────────────────────────────────────────────────
# Consumer
# ─────────────────────────────────────────────────────────────────────────────

def consume_articles(
    consumer_name: str = "worker-1",
    batch_size: int = 10,
    block_ms: int = 2000,
) -> Generator[tuple[str, RawArticle], None, None]:
    """
    Yield (message_id, RawArticle) from the Redis stream.
    Caller must ACK each message via ack_article() after processing.
    """
    r = get_redis()
    ensure_consumer_group(r)

    while True:
        try:
            messages = r.xreadgroup(
                groupname=REDIS_CONSUMER_GROUP,
                consumername=consumer_name,
                streams={REDIS_STREAM_NAME: ">"},
                count=batch_size,
                block=block_ms,
            )

            if not messages:
                continue

            for _stream, entries in messages:
                for msg_id, fields in entries:
                    try:
                        article = RawArticle(**json.loads(fields["payload"]))
                        yield msg_id, article
                    except Exception as exc:
                        logger.error(f"Failed to deserialise message {msg_id}: {exc}")
                        ack_article(r, msg_id)

        except redis.exceptions.ConnectionError:
            logger.warning("Redis connection lost — retrying in 2s...")
            time.sleep(2)


def ack_article(r: Optional[redis.Redis], msg_id: str) -> None:
    """Acknowledge a processed message so it leaves the pending-entries list."""
    if r is None:
        r = get_redis()
    r.xack(REDIS_STREAM_NAME, REDIS_CONSUMER_GROUP, msg_id)
