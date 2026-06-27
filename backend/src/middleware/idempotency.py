"""Idempotency middleware per contracts/api-design.md §15.1 (T016a).

Behavior:
- On POST requests with `Idempotency-Key` header:
  - If key unseen: process, store body_hash + response, return
  - If key seen with same body_hash: replay stored response
  - If key seen with different body_hash: return 422 PPTAGENT.IDEMPOTENCY_MISMATCH
- TTL: 24h
- Applies to write endpoints only (POST/PUT/PATCH/DELETE)
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any

from fastapi import Request, Response
from sqlalchemy import delete, select
from starlette.middleware.base import BaseHTTPMiddleware

from src.core.config import settings
from src.core.errors import IdempotencyMismatchError
from src.core.observability import get_logger
from src.db.models import IdempotencyKey, User
from src.db.session import get_session_factory

logger = get_logger("idempotency")

IDEMPOTENCY_TTL = timedelta(hours=24)
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _hash_body(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


class IdempotencyMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.method not in WRITE_METHODS:
            return await call_next(request)

        idempotency_key = request.headers.get("Idempotency-Key") or request.headers.get(
            "X-Idempotency-Key"
        )
        if not idempotency_key:
            return await call_next(request)

        # Buffer body so we can read it twice
        body = await request.body()
        body_hash = _hash_body(body)

        # Resolve current user (best-effort — auth dependency will re-check)
        factory = get_session_factory()
        async with factory() as session:
            # First, prune expired keys
            await session.execute(
                delete(IdempotencyKey).where(IdempotencyKey.expires_at < datetime.utcnow())
            )
            await session.commit()

            # Try to find existing
            result = await session.execute(
                select(IdempotencyKey).where(
                    IdempotencyKey.key == idempotency_key,
                    IdempotencyKey.method == request.method,
                    IdempotencyKey.path == request.url.path,
                )
            )
            existing = result.scalar_one_or_none()

            if existing is not None:
                if existing.body_hash != body_hash:
                    raise IdempotencyMismatchError(idempotency_key)
                # Replay stored response
                logger.info(
                    "idempotency_replay",
                    key=idempotency_key,
                    status=existing.response_status,
                )
                return Response(
                    content=json.dumps(existing.response_body or {}),
                    status_code=existing.response_status,
                    media_type="application/json",
                    headers={"X-Idempotent-Replay": "true"},
                )

        # No existing — process and persist
        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": body, "more_body": False}

        request = Request(request.scope, receive=receive)  # type: ignore[arg-type]
        response = await call_next(request)

        # Read response body
        resp_body = b""
        async for chunk in response.body_iterator:  # type: ignore[attr-defined]
            resp_body += chunk

        # Only persist successful + client-error responses (not 5xx)
        if response.status_code < 500:
            try:
                payload = json.loads(resp_body.decode("utf-8")) if resp_body else {}
            except json.JSONDecodeError:
                payload = {}

            # Determine user id from the request (set by auth dep, or by `enforce_rate_limit`)
            owner_id = getattr(request.state, "user_id", None)
            if owner_id is None:
                # Try dev key
                owner_id = await _resolve_dev_user_id()

            if owner_id is not None:
                async with factory() as session:
                    record = IdempotencyKey(
                        owner_id=owner_id,
                        key=idempotency_key,
                        method=request.method,
                        path=request.url.path,
                        body_hash=body_hash,
                        response_status=response.status_code,
                        response_body=payload,
                        expires_at=datetime.utcnow() + IDEMPOTENCY_TTL,
                    )
                    session.add(record)
                    await session.commit()
                    logger.info(
                        "idempotency_stored", key=idempotency_key, status=response.status_code
                    )

        # Reconstruct response with buffered body
        return Response(
            content=resp_body,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
        )


async def _resolve_dev_user_id() -> str | None:
    try:
        factory = get_session_factory()
        async with factory() as session:
            result = await session.execute(
                select(User).where(User.email == settings.dev_user_email)
            )
            user = result.scalar_one_or_none()
            return str(user.id) if user else None
    except Exception:  # pragma: no cover
        return None
