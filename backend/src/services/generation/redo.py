"""Stage redo service (T090) — preserve upstream, reset downstream."""

from __future__ import annotations

import uuid

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
from src.services.generation.pipeline import STAGE_ORDER, GenerationPipeline

logger = get_logger("redo")

STAGE_INDEX = {s.value: i for i, s in enumerate(STAGE_ORDER)}


async def redo_stage(session: AsyncSession, task_id: uuid.UUID, stage_name: str) -> TraceStage:
    """Re-run a stage + all downstream stages (FR-016).

    Saves the upstream outputs so they aren't re-computed (SC-009 ≥ 60% saving).
    """
    if stage_name not in STAGE_INDEX:
        raise PPTagentError(
            code="PPTAGENT.INVALID_STAGE",
            message=f"Invalid stage: {stage_name}. Must be one of: {list(STAGE_INDEX)}",
            status_code=400,
        )

    # Locate stage
    result = await session.execute(
        select(TraceStage).where(TraceStage.task_id == task_id, TraceStage.stage_name == stage_name)
    )
    stage = result.scalar_one_or_none()
    if not stage:
        raise NotFoundError("TraceStage", f"{task_id}/{stage_name}")

    # Reset this stage + all downstream
    target_idx = STAGE_INDEX[stage_name]
    downstream_stages = [s.value for s in STAGE_ORDER[target_idx:]]
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

    # Increment redo count
    stage.redo_count += 1
    await session.flush()

    # Mark task as running again
    task = (
        await session.execute(select(GenerationTask).where(GenerationTask.id == task_id))
    ).scalar_one_or_none()
    if task:
        task.status = TaskStatus.running
        task.error_message = None

    # Schedule redo in background (don't await here)
    import asyncio

    asyncio.create_task(_run_redo(task_id))

    return stage


async def _run_redo(task_id: uuid.UUID) -> None:
    """Re-execute the pipeline; upstream stages will be no-ops (already success)."""
    from src.db.session import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        pipeline = GenerationPipeline(session, str(task_id))
        await pipeline.run()
