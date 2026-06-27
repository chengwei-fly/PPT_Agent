"""PPTagent backend — FastAPI application entrypoint.

Constitution §V: All requests include three-tag context (request_id / user_id / feature).
Constitution §VI: 6-stage CI: lint → unit → contract → e2e → security → token-budget.
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from src.core.config import settings
from src.core.errors import register_error_handlers
from src.core.lifespan import lifespan
from src.core.observability import configure_observability, instrument_app
from src.middleware.idempotency import IdempotencyMiddleware
from src.middleware.request_id import RequestIdMiddleware

__version__ = "0.1.0"


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Wire up startup/shutdown hooks via src.core.lifespan."""
    async with lifespan(app):
        yield


def create_app() -> FastAPI:
    """FastAPI application factory."""
    app = FastAPI(
        title="PPTagent API",
        version=__version__,
        description="PPTagent MVP — generation / knowledge base / agent evolution",
        docs_url="/docs" if settings.app_env != "production" else None,
        redoc_url="/redoc" if settings.app_env != "production" else None,
        openapi_url="/openapi.json",
        default_response_class=ORJSONResponse,
        lifespan=_lifespan,
    )

    # ─── CORS (must be first) ────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins_list,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-Id", "X-Rate-Limit-Remaining"],
    )

    # ─── Custom middleware (order matters: outermost first) ─────────
    app.add_middleware(RequestIdMiddleware)  # T016b: X-Request-Id
    app.add_middleware(IdempotencyMiddleware)  # T016a: 24h idempotency

    # ─── Observability (Constitution §V) ─────────────────────────────
    configure_observability(app)
    instrument_app(app)

    # ─── Error handlers (RFC 7807 / contracts/error-codes.yaml) ─────
    register_error_handlers(app)

    # ─── Routers (registered lazily so missing deps don't crash startup) ─
    from src.api.assets import router as assets_router
    from src.api.credentials import router as credentials_router
    from src.api.data_lifecycle import router as data_lifecycle_router
    from src.api.drafts import router as drafts_router
    from src.api.generations import router as generations_router
    from src.api.ops import router as ops_router
    from src.api.preferences import router as preferences_router
    from src.api.samples import router as samples_router
    from src.api.security import router as security_router
    from src.api.traces import router as traces_router
    from src.api.ws import router as ws_router

    app.include_router(ops_router, prefix="/api/v1", tags=["ops"])
    app.include_router(ws_router, prefix="/ws", tags=["websocket"])
    app.include_router(generations_router, prefix="/api/v1", tags=["generations"])
    app.include_router(samples_router, prefix="/api/v1", tags=["samples"])
    app.include_router(preferences_router, prefix="/api/v1", tags=["preferences"])
    app.include_router(traces_router, prefix="/api/v1", tags=["traces"])
    app.include_router(data_lifecycle_router, prefix="/api/v1", tags=["data-lifecycle"])
    app.include_router(security_router, prefix="/api/v1", tags=["security"])
    app.include_router(assets_router, prefix="/api/v1", tags=["materials"])
    app.include_router(drafts_router, prefix="/api/v1", tags=["drafts"])
    app.include_router(credentials_router, prefix="/api/v1/credentials", tags=["credentials"])

    return app


app = create_app()


# ─── Quick sanity-check (used in healthz) ──────────────────────────────
@app.middleware("http")
async def add_process_time_header(request: Request, call_next: Any) -> Any:
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    response.headers["X-Process-Time-Ms"] = f"{duration_ms:.2f}"
    return response
