"""Celery application initialisation and beat schedule.

Start the worker:
    celery -A app.main worker --loglevel=info

Start the beat scheduler:
    celery -A app.main beat --loglevel=info
"""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.config import settings

# ── Celery application ───────────────────────────────────────────────
celery_app = Celery(
    "enjin_ingestion",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    # Serialisation
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,

    # Reliability
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,

    # Result expiry (24 h)
    result_expires=86_400,

    # Beat schedule ────────────────────────────────────────────────────
    beat_schedule={
        "fetch-rss-feeds-every-15m": {
            "task": "app.tasks.ingest.fetch_all_sources",
            "schedule": crontab(minute="*/15"),
            "kwargs": {"adapter_name": "rss"},
        },
        "fetch-gdelt-every-15m": {
            "task": "app.tasks.ingest.fetch_all_sources",
            "schedule": crontab(minute="*/15"),
            "kwargs": {"adapter_name": "gdelt"},
        },
        "process-unprocessed-items-every-5m": {
            "task": "app.tasks.ingest.process_raw_items",
            "schedule": crontab(minute="*/5"),
        },
    },
)

# Autodiscover tasks inside the app.tasks package
celery_app.autodiscover_tasks(["app.tasks"])
