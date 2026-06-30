"""Queue worker (T042) — single-user 2-concurrency gate + dynamic timeout.

The timeout scales with the page count so 50-page decks don't
hit the 5-minute ceiling. Formula::

    timeout = clamp(
        base_seconds + per_page_seconds * page_count,
        min=120,
        max=generation_timeout_max_seconds,
    )

50 pages → 60 + 3*50 = 210s. 5 pages → 75s. Note that
``extract_page_count`` caps page_count at 60 (see
``src.agents.agent_tools.extract_page_count``), so very large
prompts collapse to the 60-page branch (~240s). To support 100+
pages, raise ``extract_page_count``'s ``max_pages`` AND the
``generation_timeout_max_seconds`` ceiling together.

Resume: if a task already has ``rendered_slides`` in its
checkpoint, the agent skips those slides automatically (the
SVG tool merges by order).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from src.agents.agent_tools import extract_page_count
from src.agents.orchestrator import OrchestratorAgent
from src.core.config import settings
from src.core.observability import get_logger
from src.db.models import GenerationTask, TaskStatus
from src.db.session import get_session_factory
from src.scheduler.queue import (
    acquire_user_slot,
    dequeue_generation_task,
    release_user_slot,
)

logger = get_logger("worker")


def compute_timeout_seconds(prompt: str | None) -> int:
    """Dynamic timeout that scales with the requested page count."""
    page_count = extract_page_count(prompt or "")
    raw = (
        settings.generation_timeout_base_seconds
        + int(settings.generation_timeout_per_page_seconds * page_count)
    )
    return max(120, min(raw, settings.generation_timeout_max_seconds))


async def process_generation_task(task_id: str, owner_id: str) -> None:
    """Process a single generation task end-to-end (ReAct orchestrator)."""
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
                task.error_message = "Queue deadline exceeded"
                await session.commit()
                return

            timeout = compute_timeout_seconds(task.prompt)
            logger.info(
                "worker_task_start",
                task_id=task_id,
                page_count=extract_page_count(task.prompt),
                timeout=timeout,
            )

            # Resume hint: if we already have rendered slides, log it
            if task.rendered_slides:
                logger.info(
                    "worker_task_resume",
                    task_id=task_id,
                    already_rendered=len(task.rendered_slides),
                )

            orchestrator = OrchestratorAgent(session, task)
            await asyncio.wait_for(orchestrator.run(), timeout=timeout)
    except TimeoutError:
        logger.error("worker_timeout", task_id=task_id, timeout=timeout)
        factory = get_session_factory()
        async with factory() as session:
            task = (
                await session.execute(
                    select(GenerationTask).where(GenerationTask.id == uuid.UUID(task_id))
                )
            ).scalar_one_or_none()
            if task:
                task.status = TaskStatus.failed
                task.error_message = (
                    f"Generation exceeded dynamic timeout "
                    f"({timeout}s for {extract_page_count(task.prompt)} pages). "
                    "Re-queue to resume from checkpoint."
                )
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
