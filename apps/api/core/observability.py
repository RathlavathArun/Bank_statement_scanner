"""
Unified observability module (Sentry + OpenTelemetry).
PRD reference: Phase 2 Tasks 12 & 13.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from core.config import settings
from core.log_filter import _redact

logger = logging.getLogger(__name__)

_INITIALIZED = False


def _sentry_before_send(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any]:
    """Scrub PII from all Sentry error reports before sending to server."""
    def scrub(obj: Any) -> Any:
        if isinstance(obj, str):
            return _redact(obj)
        if isinstance(obj, dict):
            return {k: scrub(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [scrub(v) for v in obj]
        return obj

    try:
        return scrub(event)
    except Exception:  # noqa: BLE001
        return event


def init_observability(app: Optional[Any] = None, engine: Optional[Any] = None) -> None:
    """
    Initialize Sentry and OpenTelemetry instrumentation.
    Safe to call multiple times (idempotent).
    """
    global _INITIALIZED
    if _INITIALIZED:
        return

    # 1. Initialize Sentry
    if settings.SENTRY_DSN:
        try:
            import sentry_sdk
            from sentry_sdk.integrations.celery import CeleryIntegration
            from sentry_sdk.integrations.fastapi import FastAPIIntegration
            from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

            sentry_sdk.init(
                dsn=settings.SENTRY_DSN,
                environment=settings.ENVIRONMENT,
                traces_sample_rate=1.0 if settings.DEBUG else 0.2,
                send_default_pii=False,
                before_send=_sentry_before_send,
                integrations=[
                    FastAPIIntegration(),
                    CeleryIntegration(),
                    SqlalchemyIntegration(),
                ],
            )
            logger.info("Sentry initialized with environment=%s", settings.ENVIRONMENT)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to initialize Sentry: %s", exc)

    # 2. Initialize OpenTelemetry
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create({"service.name": settings.OTEL_SERVICE_NAME, "environment": settings.ENVIRONMENT})
        provider = TracerProvider(resource=resource)

        if settings.OTEL_EXPORTER_OTLP_ENDPOINT:
            try:
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
                exporter = OTLPSpanExporter(endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT)
                provider.add_span_processor(BatchSpanProcessor(exporter))
                logger.info("OpenTelemetry OTLP exporter configured for %s", settings.OTEL_EXPORTER_OTLP_ENDPOINT)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to setup OTLP exporter: %s", exc)

        trace.set_tracer_provider(provider)

        # Automatic Instrumentations
        try:
            from opentelemetry.instrumentation.botocore import BotocoreInstrumentor
            BotocoreInstrumentor().instrument()
        except Exception as exc:  # noqa: BLE001
            logger.debug("Botocore instrumentation skipped/failed: %s", exc)

        try:
            from opentelemetry.instrumentation.celery import CeleryInstrumentor
            CeleryInstrumentor().instrument()
        except Exception as exc:  # noqa: BLE001
            logger.debug("Celery instrumentation skipped/failed: %s", exc)

        try:
            from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
            if engine is not None:
                SQLAlchemyInstrumentor().instrument(engine=engine)
            else:
                SQLAlchemyInstrumentor().instrument()
        except Exception as exc:  # noqa: BLE001
            logger.debug("SQLAlchemy instrumentation skipped/failed: %s", exc)

        if app is not None:
            try:
                from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
                FastAPIInstrumentor().instrument_app(app)
            except Exception as exc:  # noqa: BLE001
                logger.debug("FastAPI instrumentation skipped/failed: %s", exc)

        logger.info("OpenTelemetry initialized with service.name=%s", settings.OTEL_SERVICE_NAME)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to initialize OpenTelemetry: %s", exc)

    _INITIALIZED = True


def get_tracer(name: str = "bank-statement-scanner"):
    try:
        from opentelemetry import trace
        return trace.get_tracer(name)
    except Exception:  # noqa: BLE001
        class DummySpan:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def set_attribute(self, *args):
                pass
            def record_exception(self, *args):
                pass

        class DummyTracer:
            def start_as_current_span(self, name, *args, **kwargs):
                return DummySpan()

        return DummyTracer()
