"""
PII-redacting log filter.

Attaches to the root logger so that account numbers, narrations containing
account-like digit sequences, and other identifiers are replaced with
[REDACTED] before any log handler emits the record.

This prevents PII from being shipped to CloudWatch / Datadog / Loki at
the INFO level.

PRD reference: Phase 1 Task 5 — "Redact account numbers and narrations from
all INFO-level logs before they reach CloudWatch. DPDP Act 2023 violation risk."

Usage (wired automatically in main.py lifespan):
    import logging
    from core.log_filter import PiiRedactFilter
    logging.getLogger().addFilter(PiiRedactFilter())
"""
from __future__ import annotations

import logging
import re

# ─── Patterns to redact from log messages ───────────────────────────────────

_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Long digit runs (account numbers, card numbers, Aadhaar)
    (re.compile(r"\b\d{9,18}\b"), "[ACCT]"),
    # Indian PAN
    (re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b", re.IGNORECASE), "[PAN]"),
    # Indian mobile numbers
    (re.compile(r"(?:\+91[\s-]?|0)?[6-9]\d{9}\b"), "[PHONE]"),
    # IFSC codes
    (re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b", re.IGNORECASE), "[IFSC]"),
    # Email addresses (may appear in log context)
    (re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"), "[EMAIL]"),
]


class PiiRedactFilter(logging.Filter):
    """
    A logging.Filter that redacts PII from log record messages.

    Applies to both the formatted message string and the raw args so that
    the redaction happens regardless of how the logger was called.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        # Redact the already-formatted message if available
        if record.getMessage:
            try:
                msg = record.getMessage()
                redacted = _redact(msg)
                # Replace args so re-formatting doesn't un-redact
                record.msg = redacted
                record.args = None
            except Exception:  # noqa: BLE001
                pass  # Never let the filter crash the app
        return True


def _redact(text: str) -> str:
    """Apply all PII patterns to a string and return the redacted version."""
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def configure_pii_logging(debug: bool = False) -> None:
    """
    Configure the root logger with PII redaction.
    Call once from the application lifespan startup.
    """
    root_logger = logging.getLogger()

    # Set level: DEBUG in dev, INFO in production
    root_logger.setLevel(logging.DEBUG if debug else logging.INFO)

    # Attach the PII filter to every existing handler (and future ones
    # added before this function is called again)
    pii_filter = PiiRedactFilter()
    for handler in root_logger.handlers:
        if not any(isinstance(f, PiiRedactFilter) for f in handler.filters):
            handler.addFilter(pii_filter)

    # Also add to root logger itself so it applies to all propagated records
    if not any(isinstance(f, PiiRedactFilter) for f in root_logger.filters):
        root_logger.addFilter(pii_filter)
