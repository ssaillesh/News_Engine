"""Celery application.

No tasks yet — the worker boots so the compose stack is complete and future
tasks have a home. Register task modules in ``include`` as they are added.
"""

from __future__ import annotations

import sys
from pathlib import Path

# The worker runs from backend/, where `app` is importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from celery import Celery  # noqa: E402

from app.config import get_settings  # noqa: E402

settings = get_settings()

celery_app = Celery(
    "research",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[],
)

celery_app.conf.update(
    task_track_started=True,
    task_time_limit=600,
    timezone="UTC",
)
