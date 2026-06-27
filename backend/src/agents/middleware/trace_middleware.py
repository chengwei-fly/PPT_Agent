"""Trace middleware — writes TraceStage rows for observability (FR-022)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.observability import get_logger
from src.db.models import StageStatus, TraceStage

logger = get_logger("trace_middleware")


class TraceMiddleware:
    """Records per-stage spans as TraceStage rows + OTel spans."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def on_stage_start(
        self,
        task_id: UUID,
        stage_name: str,
        stage_order: int,
        input_summary: str,
        referenced_sample_ids: list[UUID] | None = None,
    ) -> TraceStage:
        stage = TraceStage(
            task_id=task_id,
            stage_name=stage_name,
            stage_order=stage_order,
            input_summary=input_summary[:2000],
            output_summary="",
            referenced_sample_ids=referenced_sample_ids or [],
            duration_ms=0,
            status=StageStatus.running,
            started_at=datetime.utcnow(),
        )
        self.session.add(stage)
        await self.session.flush()
        logger.info("stage_started", task_id=str(task_id), stage=stage_name, order=stage_order)
        return stage

    async def on_stage_finish(
        self,
        stage: TraceStage,
        output_summary: str,
        status: StageStatus = StageStatus.success,
        error_message: str | None = None,
    ) -> None:
        stage.output_summary = output_summary[:2000]
        stage.status = status
        stage.error_message = error_message
        stage.finished_at = datetime.utcnow()
        if stage.started_at:
            delta = (stage.finished_at - stage.started_at).total_seconds() * 1000
            stage.duration_ms = int(delta)
        await self.session.flush()
        logger.info(
            "stage_finished",
            task_id=str(stage.task_id),
            stage=stage.stage_name,
            status=status.value,
            duration_ms=stage.duration_ms,
        )

    async def on_redo(self, stage: TraceStage) -> None:
        stage.redo_count += 1
        await self.session.flush()
        logger.info(
            "stage_redone",
            task_id=str(stage.task_id),
            stage=stage.stage_name,
            count=stage.redo_count,
        )
