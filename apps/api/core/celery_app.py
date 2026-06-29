"""Celery application configuration for background processing."""
from __future__ import annotations

from celery import Celery

from core.config import settings
from core.observability import init_observability


celery_app = Celery(
    "bank_statement_scanner",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["statements.tasks"],
)

# Initialize observability for Celery workers
init_observability()

celery_app.conf.update(
    accept_content=["json"],
    broker_connection_retry_on_startup=True,
    result_serializer="json",
    task_always_eager=settings.CELERY_TASK_ALWAYS_EAGER,
    task_eager_propagates=True,
    task_serializer="json",
    task_track_started=True,
    timezone="UTC",
)
