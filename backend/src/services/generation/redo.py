"""Stage redo service (T090) — preserve upstream, reset downstream.

In the ReAct-agent era, "redo" means: keep the upstream
``rendered_slides`` checkpoint and re-enqueue the task. The
new orchestrator will see the checkpoint in
``task.rendered_slides`` and only re-render the missing slides.

For per-slide granular redo the LLM can call ``redo_slide``
directly via the ReAct loop, so this API now exposes two
shapes:

  * ``redo_stage(task_id, stage_name)`` — old API kept for
    back-compat with the API router; re-enqueues the task.
  * ``redo_slide_checkpoint(task_id, slide_orders)`` — drops
    the named slides from the checkpoint, so a re-queue
    re-renders only them.
"""

from __future__ import annotations

import uuid
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import NotFoundError, PPTagentError
from src.core.observability import get_logger
from src.db.models import (
    GenerationTask,
    StageStatus,
    TaskStatus,
    TraceStage,
)
from src.scheduler.queue import enqueue_generation_task

logger = get_logger("redo")

# Stage names that match the original (legacy) pipeline order.
# Kept for back-compat with the API router.
LEGACY_STAGE_ORDER = ["outline", "points", "svg", "pptx"]
LEGACY_STAGE_INDEX = {n: i for i, n in enumerate(LEGACY_STAGE_ORDER)}


async def redo_stage(session: AsyncSession, task_id: uuid.UUID, stage_name: str) -> TraceStage:
    """Re-run a task; upstream checkpoint is preserved (FR-016)."""
    if stage_name not in LEGACY_STAGE_INDEX:
        raise PPTagentError(
            code="PPTAGENT.INVALID_STAGE",
            message=f"Invalid stage: {stage_name}. Must be one of: {list(LEGACY_STAGE_INDEX)}",
            status_code=400,
        )

    # Locate stage (may not exist yet — ReAct tasks don't write per-stage rows)
    result = await session.execute(
        select(TraceStage).where(
            TraceStage.task_id == task_id, TraceStage.stage_name == stage_name
        )
    )
    stage = result.scalar_one_or_none()
    if not stage:
        # Create a stub so the API contract is preserved
        from datetime import datetime

        stage = TraceStage(
            task_id=task_id,
            stage_name=stage_name,
            stage_order=LEGACY_STAGE_INDEX[stage_name] + 1,
            status=StageStatus.running,
            started_at=datetime.utcnow(),
        )
        session.add(stage)
        await session.flush()

    # Reset this stage + all downstream
    target_idx = LEGACY_STAGE_INDEX[stage_name]
    downstream_stages = LEGACY_STAGE_ORDER[target_idx:]
    downstream_result = await session.execute(
        select(TraceStage).where(
            TraceStage.task_id == task_id, TraceStage.stage_name.in_(downstream_stages)
        )
    )
    for s in downstream_result.scalars():
        s.status = StageStatus.pending
        s.started_at = None
        s.finished_at = None
        s.error_message = None
        s.output_summary = ""

    stage.redo_count += 1
    await session.flush()

    # Mark task as running again and re-enqueue
    task = (
        await session.execute(select(GenerationTask).where(GenerationTask.id == task_id))
    ).scalar_one_or_none()
    if not task:
        raise NotFoundError("GenerationTask", str(task_id))

    task.status = TaskStatus.queued
    task.error_message = None
    await session.commit()

    # Re-enqueue so the worker picks it up (orchestrator will
    # resume from the rendered_slides checkpoint).
    await enqueue_generation_task(
        task_id=str(task.id),
        owner_id=str(task.owner_id),
    )
    logger.info("redo_reenqueued", task_id=str(task.id), stage=stage_name)
    return stage


async def redo_slide_checkpoint(
    session: AsyncSession, task_id: uuid.UUID, slide_orders: Iterable[int]
) -> int:
    """Drop the named slide orders from the rendered_slides checkpoint.

    Returns the number of slides that were actually removed.
    The next worker run will re-render only those slides.
    """
    task = (
        await session.execute(select(GenerationTask).where(GenerationTask.id == task_id))
    ).scalar_one_or_none()
    if not task:
        raise NotFoundError("GenerationTask", str(task_id))

    orders = set(int(o) for o in slide_orders)
    before = list(task.rendered_slides or [])
    after = [s for s in before if s.get("order") not in orders]
    removed = len(before) - len(after)
    task.rendered_slides = after
    task.status = TaskStatus.queued
    task.error_message = None
    await session.commit()
    await enqueue_generation_task(
        task_id=str(task.id), owner_id=str(task.owner_id)
    )
    logger.info(
        "redo_slides_dropped",
        task_id=str(task.id),
        removed=removed,
        remaining=len(after),
    )
    return removed


# ─────────────────────────────────────────────────────────────────────
# Internal: legacy background loop
# ─────────────────────────────────────────────────────────────────────
async def _run_redo(task_id: uuid.UUID) -> None:
    """Re-execute the orchestrator; the rendered_slides checkpoint
    is preserved so the agent only re-renders missing slides.
    """
    from src.db.session import get_session_factory

    from src.agents.orchestrator import OrchestratorAgent

    factory = get_session_factory()
    async with factory() as session:
        from src.db.models import GenerationTask as _GT

        task = (
            await session.execute(
                select(_GT).where(_GT.id == task_id)
            )
        ).scalar_one_or_none()
        if not task:
            logger.error("redo_task_not_found", task_id=str(task_id))
            return
        orchestrator = OrchestratorAgent(session, task)
        await orchestrator.run()
