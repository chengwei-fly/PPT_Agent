"""Generation API — POST /generations, GET /generations/{id}, DELETE /generations/{id} (T043-T045)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import NotFoundError, PPTagentError
from src.core.observability import get_logger
from src.core.security import CurrentUser
from src.db.models import GenerationMode, GenerationTask, TaskStage, TaskStatus
from src.db.session import get_db_session
from src.scheduler.queue import (
    acquire_user_slot,
    enqueue_generation_task,
    publish_ws_event,
    release_user_slot,
    remove_from_queue,
)
from src.scheduler.worker import process_generation_task
from src.services.generation.token_estimator import estimate_generation

logger = get_logger("api.generations")
router = APIRouter(prefix="/generations")


# ─── DTOs ───────────────────────────────────────────────────────────
class CreateGenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(..., min_length=3, max_length=4000, description="一句话需求描述")
    sample_ids: list[uuid.UUID] = Field(
        default_factory=list, description="要纳入本次生成的样本 ID 列表（覆盖默认值）"
    )
    preferences: list[str] = Field(default_factory=list, description="要应用的首选偏好 ID")
    mode: Literal["knowledge_base", "general"] = Field(
        default="knowledge_base",
        description="生成模式：knowledge_base 基于知识库，general 通用生成",
    )
    visual_style: str | None = Field(
        default=None,
        description="视觉风格 ID（仅 general 模式）",
    )
    communication_mode: str | None = Field(
        default=None,
        description="沟通模式 ID（仅 general 模式）",
    )
    source_files: list[uuid.UUID] = Field(
        default_factory=list,
        description="上传的源文档 ID 列表（仅 general 模式）",
    )


class GenerationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    owner_id: uuid.UUID
    prompt: str
    status: TaskStatus
    current_stage: TaskStage | None
    queue_position: int | None
    estimated_tokens: int | None
    estimated_seconds: int | None
    token_consumed: int
    result_pptx_path: str | None
    style_fit_score: dict | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error_message: str | None
    mode: GenerationMode
    visual_style: str | None
    communication_mode: str | None


class QueuedGenerationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: uuid.UUID
    queue_position: int
    estimated_tokens: int
    estimated_seconds: int
    poll_url: str


# ─── Routes ────────────────────────────────────────────────────────
@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=QueuedGenerationResponse)
async def create_generation(
    body: CreateGenerationRequest,
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> QueuedGenerationResponse:
    """Queue a new generation task (FR-001). Returns 202 with queue position."""
    # Validate general mode parameters
    gen_mode = GenerationMode(body.mode)
    if gen_mode == GenerationMode.general:
        from src.services.generation.reference_loader import ReferenceLoader

        refs = ReferenceLoader()
        if body.visual_style and body.visual_style not in refs.get_style_ids():
            raise PPTagentError(
                code="PPTAGENT.INVALID_VISUAL_STYLE",
                message=f"Unknown visual style: {body.visual_style}",
                status_code=422,
            )
        if body.communication_mode and body.communication_mode not in refs.get_mode_ids():
            raise PPTagentError(
                code="PPTAGENT.INVALID_COMMUNICATION_MODE",
                message=f"Unknown communication mode: {body.communication_mode}",
                status_code=422,
            )

    # Token estimate (FR-004)
    est = estimate_generation(
        prompt=body.prompt,
        sample_count=len(body.sample_ids),
        mode=body.mode,
    )

    # Create task
    task = GenerationTask(
        owner_id=user.id,
        prompt=body.prompt,
        sample_snapshot_ids=body.sample_ids,
        mode=gen_mode,
        visual_style=body.visual_style,
        communication_mode=body.communication_mode,
        source_file_ids=body.source_files,
        status=TaskStatus.queued,
        estimated_tokens=est.tokens,
        estimated_seconds=est.seconds,
        queue_deadline_at=datetime.utcnow() + timedelta(seconds=300),
    )
    session.add(task)
    await session.flush()

    # Enqueue (Redis Stream)
    queue_pos = await enqueue_generation_task(str(task.id), str(user.id))
    task.queue_position = queue_pos
    await session.commit()

    # Try to acquire concurrency slot (FR-029: max 2/user)
    if not await acquire_user_slot(str(user.id), limit=2):
        # Notify user via WS that they're queued
        await publish_ws_event(
            f"user:{user.id}:generations",
            {
                "type": "task.queued",
                "task_id": str(task.id),
                "queue_position": queue_pos,
            },
        )
    else:
        # Slot available — process in background
        background_tasks.add_task(process_generation_task, str(task.id), str(user.id))
        await release_user_slot(str(user.id))  # release after enqueueing

    logger.info(
        "generation_queued",
        task_id=str(task.id),
        user_id=str(user.id),
        queue_pos=queue_pos,
        est_tokens=est.tokens,
    )

    return QueuedGenerationResponse(
        task_id=task.id,
        queue_position=queue_pos,
        estimated_tokens=est.tokens,
        estimated_seconds=est.seconds,
        poll_url=f"/api/v1/generations/{task.id}",
    )


@router.get("/{task_id}", response_model=GenerationResponse)
async def get_generation(
    task_id: uuid.UUID,
    user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> GenerationTask:
    result = await session.execute(
        select(GenerationTask).where(
            GenerationTask.id == task_id,
            GenerationTask.owner_id == user.id,
            GenerationTask.finished_at.is_(None) | (GenerationTask.finished_at != None),  # noqa: E711
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise NotFoundError("GenerationTask", str(task_id))
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_generation(
    task_id: uuid.UUID,
    user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Cancel a queued or running task (FR-003, must take effect within 5s)."""
    result = await session.execute(
        select(GenerationTask).where(
            GenerationTask.id == task_id, GenerationTask.owner_id == user.id
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise NotFoundError("GenerationTask", str(task_id))
    if task.status not in (TaskStatus.queued, TaskStatus.running):
        return  # No-op for already-completed
    task.status = TaskStatus.cancelled
    task.finished_at = datetime.utcnow()
    await session.commit()
    await remove_from_queue(str(task_id))
    await publish_ws_event(
        f"task:{task_id}",
        {"type": "task.cancelled", "task_id": str(task_id), "ts": datetime.utcnow().isoformat()},
    )
    logger.info("generation_cancelled", task_id=str(task_id), user_id=str(user.id))


# ─── Style & mode discovery ────────────────────────────────────────
@router.get("/styles")
async def list_visual_styles() -> list[dict[str, str]]:
    """List available visual styles for general mode."""
    from src.services.generation.reference_loader import ReferenceLoader

    return ReferenceLoader().list_visual_styles()


@router.get("/modes")
async def list_communication_modes() -> list[dict[str, str]]:
    """List available communication modes for general mode."""
    from src.services.generation.reference_loader import ReferenceLoader

    return ReferenceLoader().list_communication_modes()
