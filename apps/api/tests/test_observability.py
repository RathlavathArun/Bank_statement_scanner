"""
tests/test_observability.py — Unit tests for OpenTelemetry and Sentry integration.
"""
from __future__ import annotations

import pytest
from core.observability import init_observability, get_tracer, _sentry_before_send


def test_init_observability_does_not_crash():
    """Verify that calling init_observability succeeds without error."""
    init_observability()


def test_get_tracer_returns_usable_tracer():
    """Verify that get_tracer returns a tracer capable of starting spans."""
    tracer = get_tracer("test-tracer")
    with tracer.start_as_current_span("test_span") as span:
        span.set_attribute("key", "value")


def test_sentry_before_send_redacts_pii():
    """Verify that the Sentry before_send callback redacts PII from error payloads."""
    event = {
        "message": "Error processing user@example.com with account 123456789012",
        "extra": {
            "phone": "9876543210",
        },
    }
    scrubbed = _sentry_before_send(event, {})
    assert "user@example.com" not in scrubbed["message"]
    assert "123456789012" not in scrubbed["message"]
    assert "9876543210" not in str(scrubbed["extra"])
