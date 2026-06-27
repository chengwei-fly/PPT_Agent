"""Trace API — GET /generations/{id}/trace, POST .../stages/{name}/redo (T088-T089)."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import NotFoundError
from src.core.observability import get_logger
from src.core.security import CurrentUser
from src.db.models import GenerationTask, StageStatus, TraceStage
from src.db.session import get_db_session
from src.scheduler.queue import publish_ws_event
from src.services.generation.redo import redo_stage

logger = get_logger("api.traces")
router = APIRouter(prefix="/generations")


class TraceStageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    task_id: uuid.UUID
    stage_name: str
    stage_order: int
    input_summary: str
    output_summary: str
    referenced_sample_ids: list[uuid.UUID]
    duration_ms: int
    status: StageStatus
    started_at: datetime | None
    finished_at: datetime | None
    error_message: str | None
    redo_count: int


@router.get("/{task_id}/trace", response_model=list[TraceStageResponse])
async def get_trace(
    task_id: uuid.UUID,
    user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> list[TraceStage]:
    """Return all 4 stages for a task, ordered by stage_order (FR-015)."""
    # Verify ownership
    task = (
        await session.execute(
            select(GenerationTask).where(
                GenerationTask.id == task_id, GenerationTask.owner_id == user.id
            )
        )
    ).scalar_one_or_none()
    if not task:
        raise NotFoundError("GenerationTask", str(task_id))

    result = await session.execute(
        select(TraceStage)
        .where(TraceStage.task_id == task_id)
        .order_by(TraceStage.stage_order.asc())
    )
    return list(result.scalars())


@router.post(
    "/{task_id}/stages/{stage_name}/redo",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=TraceStageResponse,
)
async def redo_stage_endpoint(
    task_id: uuid.UUID,
    stage_name: str,
    user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> TraceStage:
    """Re-run a specific stage + downstream (FR-016 / SC-009 ≥ 60% saving)."""
    task = (
        await session.execute(
            select(GenerationTask).where(
                GenerationTask.id == task_id, GenerationTask.owner_id == user.id
            )
        )
    ).scalar_one_or_none()
    if not task:
        raise NotFoundError("GenerationTask", str(task_id))

    updated_stage = await redo_stage(session, task_id, stage_name)
    await session.commit()

    await publish_ws_event(
        f"task:{task_id}",
        {
            "type": "stage.redo.started",
            "task_id": str(task_id),
            "stage": stage_name,
            "ts": datetime.utcnow().isoformat(),
        },
    )
    return updated_stage
