"""Cron jobs (T236 / T102)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from sqlalchemy import select, update

from src.core.config import settings
from src.core.observability import get_logger
from src.db.models import GenerationTask, TaskStatus
from src.db.session import get_session_factory
from src.services.draft.lock import release_expired_locks

logger = get_logger("cron")


async def release_expired_draft_locks() -> int:
    """T236: every 5 minutes, release expired draft locks."""
    factory = get_session_factory()
    async with factory() as session:
        return await release_expired_locks(session)


async def archive_old_tasks() -> int:
    """T102 / SC-013: 14d notify + 180d archive."""
    factory = get_session_factory()
    async with factory() as session:
        # Notify tasks approaching expiry
        notify_threshold = datetime.utcnow() + timedelta(days=settings.task_notify_before_days)
        await session.execute(
            update(GenerationTask)
            .where(
                GenerationTask.status == TaskStatus.success,
                GenerationTask.expires_at.is_not(None),
                GenerationTask.expires_at <= notify_threshold,
                GenerationTask.notified_at.is_(None),
            )
            .values(notified_at=datetime.utcnow())
        )
        # Archive tasks past retention
        cutoff = datetime.utcnow() - timedelta(days=settings.task_retention_days)
        result = await session.execute(
            update(GenerationTask)
            .where(
                GenerationTask.status == TaskStatus.success,
                GenerationTask.expires_at.is_not(None),
                GenerationTask.expires_at <= cutoff,
                GenerationTask.notified_at.is_not(None),  # 2-step: notify first, then archive
            )
            .values(status=TaskStatus.archived)
            .returning(GenerationTask.id)
        )
        archived = len(result.fetchall())
        await session.commit()
        if archived:
            logger.info("tasks_archived", count=archived, cutoff_days=settings.task_retention_days)
        return archived


async def hard_delete_overdue_users() -> int:
    """T101 / SC-005: users who requested delete-all > 7d ago → hard delete."""
    factory = get_session_factory()
    async with factory() as session:
        from src.db.models import User

        cutoff = datetime.utcnow() - timedelta(days=settings.task_purge_delay_days)
        # Find users who soft-deleted > 7d ago
        result = await session.execute(
            select(User).where(
                User.deleted_at.is_not(None),
                User.deleted_at <= cutoff,
            )
        )
        purged = 0
        for user in result.scalars():
            # Hard delete user (cascade via FKs)
            await session.delete(user)
            purged += 1
        await session.commit()
        if purged:
            logger.info("users_hard_deleted", count=purged)
        return purged


async def main_cron_loop() -> None:
    """Long-running cron tick loop."""
    logger.info("cron_loop_started")
    while True:
        try:
            await release_expired_draft_locks()
            await archive_old_tasks()
            await hard_delete_overdue_users()
        except Exception as e:
            logger.exception("cron_loop_error", error=str(e))
        await asyncio.sleep(300)  # 5 min
