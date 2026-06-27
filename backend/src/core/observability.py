"""OpenTelemetry + structured JSON logging per Constitution §V.

All logs MUST include three tags:
- request_id (X-Request-Id)
- user_id
- feature (e.g. "generation", "knowledge_base")
"""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING

import structlog
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from pythonjsonlogger import jsonlogger

from src.core.config import settings

if TYPE_CHECKING:
    from fastapi import FastAPI

_initialized = False


def configure_observability(app: FastAPI) -> None:
    """Configure logging + OTel once at startup.

    Idempotent: safe to call multiple times.
    """
    global _initialized
    if _initialized:
        return

    # ── Structured JSON logging ──────────────────────────────────
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        timestamper,
    ]

    if settings.log_format == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=False)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, settings.log_level)),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    # Stdlib logging → JSON (so 3rd-party libs also produce JSON)
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(name)s %(levelname)s %(message)s",
        rename_fields={"asctime": "ts", "levelname": "level"},
    )
    handler.setFormatter(formatter)
    root.addHandler(handler)
    root.setLevel(getattr(logging, settings.log_level))

    # ── OpenTelemetry ────────────────────────────────────────────
    if not settings.is_test:
        resource = Resource.create({SERVICE_NAME: settings.otel_service_name})
        provider = TracerProvider(
            resource=resource,
            sampler=trace.sampling.get_sampler(
                f"{settings.otel_traces_sampler}={settings.otel_traces_sampler_arg}"
            ),
        )
        exporter = OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

    _initialized = True


def instrument_app(app: FastAPI) -> None:
    """Auto-instrument FastAPI for tracing."""
    if settings.is_test:
        return
    FastAPIInstrumentor.instrument_app(app)


def get_tracer(name: str = "pptagent") -> trace.Tracer:
    return trace.get_tracer(name)


def shutdown_observability() -> None:
    """Flush traces on shutdown."""
    try:
        provider = trace.get_tracer_provider()
        if hasattr(provider, "shutdown"):
            provider.shutdown()  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover
        pass


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name or settings.log_namespace)


# ── Feature-specific loggers (T271) ────────────────────────────────


def get_material_logger() -> structlog.stdlib.BoundLogger:
    """Logger for material operations (indexing, search, delete)."""
    return structlog.get_logger("pptagent.material")


def get_draft_logger() -> structlog.stdlib.BoundLogger:
    """Logger for draft operations (CRUD, lock, export)."""
    return structlog.get_logger("pptagent.draft")


def get_generation_logger() -> structlog.stdlib.BoundLogger:
    """Logger for generation pipeline events."""
    return structlog.get_logger("pptagent.generation")


def get_security_logger() -> structlog.stdlib.BoundLogger:
    """Logger for security events (PII, auth, data lifecycle)."""
    return structlog.get_logger("pptagent.security")
