"""X-Request-Id middleware (T016b).

Client may optionally send X-Request-Id; server MUST generate and echo it back.
The request id is bound to the OTel trace so all logs/traces for a request can
be correlated.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

import structlog
from opentelemetry import trace
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-Id"


def _generate_request_id() -> str:
    return uuid.uuid4().hex


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Use client-supplied id if valid (length 8-128, hex/alphanum) else generate
        client_id = request.headers.get(REQUEST_ID_HEADER)
        request_id = client_id if _is_valid_id(client_id) else _generate_request_id()

        # Bind to OTel trace (use current trace id when available, else request id)
        span = trace.get_current_span()
        if span is not None and span.is_recording():
            span.set_attribute("request_id", request_id)
        span_ctx = trace.get_current_span().get_span_context()
        if span_ctx and span_ctx.is_valid:
            trace_id_hex = format(span_ctx.trace_id, "032x")
        else:
            trace_id_hex = request_id

        # Bind to structlog context vars so every log line carries the id
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            trace_id=trace_id_hex,
        )

        request.state.request_id = request_id
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        response.headers["X-Trace-Id"] = trace_id_hex
        structlog.contextvars.clear_contextvars()
        return response


def _is_valid_id(value: str | None) -> bool:
    if not value:
        return False
    if not 8 <= len(value) <= 128:
        return False
    return all(c.isalnum() or c in "-_" for c in value)
