"""Data lifecycle — delete-all service (T101 / FR-009 + FR-019)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.observability import get_logger
from src.db.models import (
    ApiKey,
    Draft,
    Embedding,
    GenerationTask,
    IdempotencyKey,
    ParseResult,
    Preference,
    Sample,
    SecurityAction,
    SecurityEvent,
    SecurityEventType,
    SlideAsset,
    TraceStage,
)

logger = get_logger("data.delete")


async def delete_all_user_data(user_id: str, session: AsyncSession) -> str:
    """Cascade-delete all user data per FR-009 三类数据分离.

    This is the immediate (soft) phase. A separate backup-purge worker
    (T102) handles the 7d backup cleanup.
    """
    uid = uuid.UUID(user_id)

    # 1. Audit FIRST (so we have a record of the deletion)
    session.add(
        SecurityEvent(
            owner_id=uid,
            event_type=SecurityEventType.bulk_delete,
            action_taken=SecurityAction.allow,
            details={"requested_at": datetime.utcnow().isoformat()},
        )
    )

    # 2. Cascade deletes — order matters (FK constraints)
    # GenerationTask → TraceStage
    tasks_subq = session.query(GenerationTask.id).filter(GenerationTask.owner_id == uid)
    await session.execute(delete(TraceStage).where(TraceStage.task_id.in_(tasks_subq)))
    # Sample → ParseResult, Embedding, SlideAsset
    samples_subq = session.query(Sample.id).filter(Sample.owner_id == uid)
    await session.execute(delete(ParseResult).where(ParseResult.sample_id.in_(samples_subq)))
    await session.execute(delete(Embedding).where(Embedding.sample_id.in_(samples_subq)))
    await session.execute(delete(SlideAsset).where(SlideAsset.source_sample_id.in_(samples_subq)))
    # Draft → DraftSlide (cascade handled by ORM)
    drafts_subq = session.query(Draft.id).filter(Draft.owner_id == uid)
    for d in (await session.execute(drafts_subq)).scalars():
        await session.delete(d)
    # Top-level rows
    await session.execute(delete(GenerationTask).where(GenerationTask.owner_id == uid))
    await session.execute(delete(Sample).where(Sample.owner_id == uid))
    await session.execute(delete(Preference).where(Preference.owner_id == uid))
    await session.execute(delete(IdempotencyKey).where(IdempotencyKey.owner_id == uid))
    # API keys
    await session.execute(delete(ApiKey).where(ApiKey.owner_id == uid))
    # SecurityEvent retention: keep 30 days for audit, then prune via cron
    # (do NOT delete immediately — required for compliance)

    # 3. Soft-delete the user
    from src.db.models import User

    user = (await session.execute(session.query(User).filter(User.id == uid))).scalar_one_or_none()
    if user:
        user.deleted_at = datetime.utcnow()
        user.email = f"deleted_{uid}@pptagent.local"  # anonymize

    await session.commit()

    job_id = str(uuid.uuid4())
    logger.info("user_data_deleted", user_id=user_id, job_id=job_id)
    return job_id
