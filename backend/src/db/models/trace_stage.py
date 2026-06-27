"""TraceStage ORM model per data-model.md §7."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    ARRAY,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.models.base import GUID, Base


class StageStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    success = "success"
    failed = "failed"


class TraceStage(Base):
    __tablename__ = "trace_stages"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("generation_tasks.id", ondelete="CASCADE"), nullable=False
    )
    stage_name: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # outline / points / svg / pptx
    stage_order: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    input_summary: Mapped[str] = mapped_column(Text, nullable=False)
    output_summary: Mapped[str] = mapped_column(Text, nullable=False)
    referenced_sample_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(GUID()), nullable=False, default=list
    )
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[StageStatus] = mapped_column(
        Enum(StageStatus, name="stage_status"), nullable=False, default=StageStatus.pending
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    redo_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    task = relationship("GenerationTask", back_populates="trace_stages")

    __table_args__ = (UniqueConstraint("task_id", "stage_name", name="uq_trace_task_stage"),)
