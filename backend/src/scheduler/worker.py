"""Queue worker (T042) — single-user 2-concurrency gate + 5min deadline."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from src.core.observability import get_logger
from src.db.models import GenerationTask, TaskStatus
from src.db.session import get_session_factory
from src.scheduler.queue import (
    acquire_user_slot,
    dequeue_generation_task,
    release_user_slot,
)
from src.services.generation.pipeline import GenerationPipeline

logger = get_logger("worker")


async def process_generation_task(task_id: str, owner_id: str) -> None:
    """Process a single generation task end-to-end (FR-029 + 5min timeout)."""
    await acquire_user_slot(owner_id, limit=2)
    try:
        factory = get_session_factory()
        async with factory() as session:
            task = (
                await session.execute(
                    select(GenerationTask).where(GenerationTask.id == uuid.UUID(task_id))
                )
            ).scalar_one_or_none()
            if not task:
                logger.error("worker_task_not_found", task_id=task_id)
                return
            if task.status not in (TaskStatus.queued, TaskStatus.running):
                logger.info("worker_task_skip", task_id=task_id, status=task.status.value)
                return
            if task.queue_deadline_at and task.queue_deadline_at < datetime.now(timezone.utc):
                task.status = TaskStatus.cancelled
                task.error_message = "Queue deadline exceeded (5min)"
                await session.commit()
                return
            pipeline = GenerationPipeline(session, task_id)
            await asyncio.wait_for(pipeline.run(), timeout=300)
    except TimeoutError:
        logger.error("worker_timeout", task_id=task_id)
        factory = get_session_factory()
        async with factory() as session:
            task = (
                await session.execute(
                    select(GenerationTask).where(GenerationTask.id == uuid.UUID(task_id))
                )
            ).scalar_one_or_none()
            if task:
                task.status = TaskStatus.failed
                task.error_message = "Generation exceeded 5min timeout (SC-001)"
                task.finished_at = datetime.now(timezone.utc)
                await session.commit()
    except Exception as e:
        logger.exception("worker_failed", task_id=task_id, error=str(e))
    finally:
        await release_user_slot(owner_id)


async def main_worker_loop() -> None:
    """Long-running consumer loop. Used when running as `worker` service."""
    logger.info("worker_loop_started")
    while True:
        try:
            msg = await dequeue_generation_task(timeout_ms=1000)
            if msg is None:
                await asyncio.sleep(0.1)
                continue
            task_id = msg.get("task_id")
            owner_id = msg.get("owner_id")
            if task_id and owner_id:
                await process_generation_task(task_id, owner_id)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.exception("worker_loop_error", error=str(e))
            await asyncio.sleep(1)
