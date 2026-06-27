"""Draft single-writer lock (T231 / R10)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import PPTagentError
from src.core.observability import get_logger
from src.db.models import Draft

logger = get_logger("draft.lock")

LOCK_TTL = timedelta(minutes=30)


def is_locked_by_other(draft: Draft, user_id: uuid.UUID) -> bool:
    if draft.editor_user_id is None or draft.editor_user_id == user_id:
        return False
    if draft.lock_expires_at and draft.lock_expires_at < datetime.utcnow():
        return False  # Expired
    return True


def is_owned_by_user(draft: Draft, user_id: uuid.UUID) -> bool:
    return draft.owner_id == user_id


async def acquire_lock(
    session: AsyncSession,
    draft_id: uuid.UUID,
    owner_id: uuid.UUID,
    editor_user_id: uuid.UUID,
    ttl: timedelta = LOCK_TTL,
) -> Draft:
    draft = (
        await session.execute(
            select(Draft).where(
                Draft.id == draft_id, Draft.owner_id == owner_id, Draft.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if not draft:
        raise PPTagentError(
            code="PPTAGENT.NOT_FOUND",
            message=f"Draft {draft_id} not found",
            status_code=404,
        )
    if is_locked_by_other(draft, editor_user_id):
        raise PPTagentError(
            code="PPTAGENT.DRAFT_LOCKED",
            message="Draft is locked by another writer",
            status_code=423,
        )
    draft.editor_user_id = editor_user_id
    draft.lock_acquired_at = datetime.utcnow()
    draft.lock_expires_at = datetime.utcnow() + ttl
    await session.flush()
    return draft


async def release_lock(session: AsyncSession, draft_id: uuid.UUID, user_id: uuid.UUID) -> None:
    draft = (
        await session.execute(select(Draft).where(Draft.id == draft_id, Draft.owner_id == user_id))
    ).scalar_one_or_none()
    if not draft:
        return
    if draft.editor_user_id == user_id:
        draft.editor_user_id = None
        draft.lock_acquired_at = None
        draft.lock_expires_at = None
        await session.flush()


async def release_expired_locks(session: AsyncSession) -> int:
    """Cron-callable: release all expired locks."""
    from sqlalchemy import update

    result = await session.execute(
        update(Draft)
        .where(
            Draft.editor_user_id.is_not(None),
            Draft.lock_expires_at < datetime.utcnow(),
        )
        .values(editor_user_id=None, lock_acquired_at=None, lock_expires_at=None)
        .returning(Draft.id)
    )
    released = len(result.fetchall())
    await session.commit()
    if released:
        logger.info("expired_locks_released", count=released)
    return released
