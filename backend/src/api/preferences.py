"""Preferences API — GET /preferences, PATCH /preferences/{id}, DELETE /preferences/{id} (T081-T082)."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import NotFoundError
from src.core.observability import get_logger
from src.core.security import CurrentUser
from src.db.models import Preference, PreferenceScope
from src.db.session import get_db_session

logger = get_logger("api.preferences")
router = APIRouter(prefix="/preferences")


class PreferenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: str
    owner_id: uuid.UUID
    source_chains: dict
    rule_text: str
    applies_to: PreferenceScope
    apply_count: int
    ignore_count: int
    last_applied_at: datetime | None
    is_active: bool
    created_at: datetime


class UpdatePreferenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_active: bool | None = None
    rule_text: str | None = None


@router.get("", response_model=list[PreferenceResponse])
async def list_preferences(
    user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[Preference]:
    """List active preferences for current user (FR-013). Sorted by apply_count DESC."""
    result = await session.execute(
        select(Preference)
        .where(
            Preference.owner_id == user.id,
            Preference.is_active.is_(True),
            Preference.deleted_at.is_(None),
        )
        .order_by(Preference.apply_count.desc(), Preference.last_applied_at.desc().nullslast())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars())


@router.patch("/{preference_id}", response_model=PreferenceResponse)
async def update_preference(
    preference_id: str,
    body: UpdatePreferenceRequest,
    user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> Preference:
    """Update a preference (toggle is_active, edit rule_text)."""
    result = await session.execute(
        select(Preference).where(
            Preference.id == preference_id,
            Preference.owner_id == user.id,
            Preference.deleted_at.is_(None),
        )
    )
    pref = result.scalar_one_or_none()
    if not pref:
        raise NotFoundError("Preference", preference_id)
    if body.is_active is not None:
        pref.is_active = body.is_active
    if body.rule_text is not None:
        pref.rule_text = body.rule_text
    await session.commit()
    logger.info("preference_updated", pref_id=preference_id, user_id=str(user.id))
    return pref


@router.delete("/{preference_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_preference(
    preference_id: str,
    user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Soft-delete a preference (FR-013)."""
    result = await session.execute(
        select(Preference).where(
            Preference.id == preference_id,
            Preference.owner_id == user.id,
            Preference.deleted_at.is_(None),
        )
    )
    pref = result.scalar_one_or_none()
    if not pref:
        raise NotFoundError("Preference", preference_id)
    pref.is_active = False
    pref.deleted_at = datetime.utcnow()
    await session.commit()
    logger.info("preference_deleted", pref_id=preference_id, user_id=str(user.id))
