"""Custom Prometheus metrics for bank statement extraction monitoring."""
from __future__ import annotations

import logging
from prometheus_client import Counter

logger = logging.getLogger(__name__)

# Counters for tracking extraction success and failure rates per bank template
EXTRACTION_TOTAL = Counter(
    "bank_extraction_total",
    "Total statement extraction attempts per bank",
    ["bank_code"]
)

EXTRACTION_FAILURES = Counter(
    "bank_extraction_failures_total",
    "Total statement extraction failures per bank",
    ["bank_code"]
)


def record_extraction_success(bank_code: str | None) -> None:
    """Record a successful statement extraction for the given bank."""
    try:
        code = (bank_code or "unknown").lower()
        EXTRACTION_TOTAL.labels(bank_code=code).inc()
    except Exception as exc:
        logger.error("Failed to record extraction success metric: %s", exc)


def record_extraction_failure(bank_code: str | None) -> None:
    """Record a failed statement extraction for the given bank."""
    try:
        code = (bank_code or "unknown").lower()
        EXTRACTION_TOTAL.labels(bank_code=code).inc()
        EXTRACTION_FAILURES.labels(bank_code=code).inc()
    except Exception as exc:
        logger.error("Failed to record extraction failure metric: %s", exc)
