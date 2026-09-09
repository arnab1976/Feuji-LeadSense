"""Celery application.

CELERY_TASK_ALWAYS_EAGER=true (the default) runs tasks inline, so the API works
without a broker. Set it to false and start the worker for real async behaviour.
"""
from celery import Celery

from app.core.config import settings

celery = Celery(
    "leadsense",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.tasks"],
)

celery.conf.update(
    task_always_eager=settings.celery_task_always_eager,
    task_eager_propagates=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_queue="default",
    task_routes={
        "leadsense.extract_batch": {"queue": "extraction"},
        "leadsense.sync_source": {"queue": "extraction"},
        "leadsense.send_campaign": {"queue": "delivery"},
    },
    beat_schedule={
        "sync-enabled-sources-hourly": {
            "task": "leadsense.sync_all_sources",
            "schedule": 3600.0,
        },
    },
)
