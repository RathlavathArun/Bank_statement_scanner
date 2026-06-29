"""Redis-backed job progress helpers used by API and Celery workers."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import redis

from core.config import settings

logger = logging.getLogger(__name__)
JOB_TTL_SECONDS = 60 * 60 * 24


def _client() -> redis.Redis:
    return redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)


def update_job_progress(
    job_id: str,
    *,
    job_type: str,
    status: str,
    stage: str,
    progress: int,
    statement_id: str | None = None,
    export_id: str | None = None,
    detail: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "job_id": job_id,
        "job_type": job_type,
        "status": status,
        "stage": stage,
        "progress": max(0, min(int(progress), 100)),
        "statement_id": statement_id,
        "export_id": export_id,
        "detail": detail,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if extra:
        payload.update(extra)

    try:
        _client().setex(f"job:{job_id}", JOB_TTL_SECONDS, json.dumps(payload, default=str))
    except Exception as exc:  # noqa: BLE001
        logger.debug("Could not write job progress to Redis: %s", exc)
    return payload


def get_job_progress(job_id: str) -> dict[str, Any] | None:
    try:
        raw = _client().get(f"job:{job_id}")
    except Exception as exc:  # noqa: BLE001
        logger.debug("Could not read job progress from Redis: %s", exc)
        return None
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None
