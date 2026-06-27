"""Security events API — GET /security/events (T106)."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.pagination import CursorPage, decode_cursor, encode_cursor
from src.core.observability import get_logger
from src.core.security import CurrentUser
from src.db.models import SecurityAction, SecurityEvent, SecurityEventType
from src.db.session import get_db_session

logger = get_logger("api.security")
router = APIRouter(prefix="/security")


class SecurityEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    event_type: SecurityEventType
    hit_field: str | None
    action_taken: SecurityAction
    related_resource_id: uuid.UUID | None
    created_at: datetime
    details: dict | None


@router.get("/events", response_model=CursorPage[SecurityEventResponse])
async def list_events(
    user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
    cursor: str | None = Query(None, description="Opaque pagination cursor"),
    limit: int = Query(50, ge=1, le=200),
    event_type: SecurityEventType | None = Query(None, description="Filter by event type"),
) -> CursorPage[SecurityEventResponse]:
    """List user's security events (FR-020). Cursor pagination per T016c."""
    decoded = decode_cursor(cursor) if cursor else None

    query = select(SecurityEvent).where(SecurityEvent.owner_id == user.id)
    if event_type:
        query = query.where(SecurityEvent.event_type == event_type)
    if decoded and "id" in decoded:
        # Cursor: fetch events older than this id
        from sqlalchemy import tuple_

        query = query.where(
            tuple_(SecurityEvent.created_at, SecurityEvent.id)
            < tuple_(datetime.fromisoformat(decoded["created_at"]), uuid.UUID(decoded["id"]))
        )
    query = query.order_by(SecurityEvent.created_at.desc(), SecurityEvent.id.desc()).limit(
        limit + 1
    )

    result = await session.execute(query)
    rows = list(result.scalars())

    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = None
    if has_more and rows:
        last = rows[-1]
        next_cursor = encode_cursor({"id": str(last.id), "created_at": last.created_at.isoformat()})

    return CursorPage(items=rows, next_cursor=next_cursor, has_more=has_more)
