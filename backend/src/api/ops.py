"""Health check + Prometheus metrics (T110 / FR-023)."""

from __future__ import annotations

from fastapi import APIRouter, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

from src.core.config import settings
from src.core.observability import get_logger
from src.models import HealthResponse
from src.scheduler.queue import get_client

router = APIRouter()
logger = get_logger("ops")

# ─── Prometheus metrics (FR-023) ──────────────────────────────────
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "status", "feature"],
)
generation_duration_seconds = Histogram(
    "generation_duration_seconds",
    "End-to-end generation duration",
    buckets=(10, 30, 60, 120, 180, 240, 300),
)
queue_length = Gauge("queue_length", "Current queue length")
tokens_consumed_total = Counter(
    "tokens_consumed_total",
    "Total tokens consumed",
    ["feature", "model"],
)
material_search_duration_seconds = Histogram(
    "material_search_duration_seconds",
    "Material search latency",
    buckets=(0.05, 0.1, 0.25, 0.5, 0.75, 1.0, 2.0),
)
draft_slide_inserted_total = Counter(
    "draft_slide_inserted_total",
    "Draft slide insertions",
    ["source_type"],
)
material_indexed_total = Counter(
    "material_indexed_total",
    "Indexed material assets",
    ["visual_type"],
)
draft_exported_total = Counter(
    "draft_exported_total",
    "Drafts exported",
    ["owner_tier"],
)


@router.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:
    db_ok = True
    redis_ok = True
    s3_ok = True
    queue_len = 0
    try:
        client = get_client()
        queue_len = int(await client.xlen("stream:generation:tasks"))
    except Exception:
        redis_ok = False
    return HealthResponse(
        status="ok" if (db_ok and redis_ok) else "degraded",
        version=settings.app_version,
        queue_length=queue_len,
        db_ok=db_ok,
        redis_ok=redis_ok,
        s3_ok=s3_ok,
    )


@router.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
