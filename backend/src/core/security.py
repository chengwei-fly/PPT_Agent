"""API Key auth + rate-limit + scope check (T017).

Constitution §IV: API 最小权限.
"""

from __future__ import annotations

import hashlib
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.errors import ForbiddenError, RateLimitError, UnauthorizedError
from src.core.observability import get_logger
from src.db.models import ApiKey, User
from src.db.session import get_db_session
from src.scheduler.queue import check_rate_limit

logger = get_logger("auth")


def hash_api_key(raw_key: str) -> str:
    """SHA-256(api_key) per data-model.md §1a."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


async def get_api_key_from_header(
    authorization: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header()] = None,
) -> str:
    """Extract bearer token (or X-Api-Key) from request headers."""
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    if x_api_key:
        return x_api_key.strip()
    raise UnauthorizedError("Missing API key (Authorization: Bearer ... or X-Api-Key)")


async def authenticate_user(
    raw_key: Annotated[str, Depends(get_api_key_from_header)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> User:
    """Resolve the API key to a User, raise UnauthorizedError on failure."""
    if not raw_key:
        raise UnauthorizedError("Empty API key")

    # Dev shortcut: pre-baked dev key maps to the dev user (dev/staging only)
    if settings.app_env != "production" and raw_key == settings.dev_api_key:
        result = await session.execute(
            select(User).where(User.email == settings.dev_user_email, User.deleted_at.is_(None))
        )
        user = result.scalar_one_or_none()
        if not user:
            # Auto-create dev user on first use
            user = User(
                email=settings.dev_user_email,
                display_name="Dev User",
                api_key_hash=hash_api_key(settings.dev_api_key),
            )
            session.add(user)
            await session.flush()
        return user

    key_hash = hash_api_key(raw_key)
    result = await session.execute(
        select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.revoked_at.is_(None))
    )
    api_key = result.scalar_one_or_none()
    if not api_key:
        raise UnauthorizedError("Invalid API key")
    if api_key.expires_at and api_key.expires_at < _now():
        raise UnauthorizedError("API key expired")

    result = await session.execute(
        select(User).where(User.id == api_key.owner_id, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise UnauthorizedError("API key owner not found")

    # Update last_used_at (best-effort)
    api_key.last_used_at = _now()
    await session.commit()
    return user


def _now():
    from datetime import datetime

    return datetime.utcnow()


def require_scope(*required_scopes: str):
    """FastAPI dependency factory: enforce API key scopes."""

    async def _checker(
        user: Annotated[User, Depends(authenticate_user)],
        raw_key: Annotated[str, Depends(get_api_key_from_header)],
        session: Annotated[AsyncSession, Depends(get_db_session)],
    ) -> User:
        if not required_scopes:
            return user
        # Dev user has all scopes (dev/staging only)
        if settings.app_env != "production" and user.email == settings.dev_user_email:
            return user
        # Look up the API key's scopes
        key_hash = hash_api_key(raw_key)
        result = await session.execute(
            select(ApiKey.scopes).where(ApiKey.key_hash == key_hash, ApiKey.revoked_at.is_(None))
        )
        row = result.scalar_one_or_none()
        granted_scopes: set[str] = set(row) if row else set()
        missing = set(required_scopes) - granted_scopes
        if missing:
            raise ForbiddenError(f"Missing required scopes: {', '.join(sorted(missing))}")
        return user

    return _checker


async def enforce_rate_limit(
    request: Request,
    user: Annotated[User, Depends(authenticate_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> User:
    """Per-user rate limit (default 60 req/min) + per-user concurrency gate (FR-029)."""
    # Query rate limit from DB to avoid lazy-loading user.api_keys in async context
    result = await session.execute(
        select(ApiKey.rate_limit_per_min)
        .where(ApiKey.owner_id == user.id, ApiKey.revoked_at.is_(None))
        .limit(1)
    )
    rate_limit = result.scalar_one_or_none() or settings.rate_limit_per_min
    allowed, retry_after = await check_rate_limit(
        user_id=str(user.id),
        limit_per_min=rate_limit,
    )
    if not allowed:
        raise RateLimitError(retry_after=retry_after)
    request.state.user_id = str(user.id)
    request.state.user_email = user.email
    return user


# ─── Helpers ────────────────────────────────────────────────────────
CurrentUser = Annotated[User, Depends(enforce_rate_limit)]
OptionalUser = Annotated[User | None, Depends(authenticate_user)]
