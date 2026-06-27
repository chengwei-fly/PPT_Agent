"""GenerationTask ORM model per data-model.md §6."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import ARRAY, DateTime, Enum, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.models.base import GUID, Base, TimestampMixin


class TaskStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    success = "success"
    failed = "failed"
    cancelled = "cancelled"
    archived = "archived"


class TaskStage(str, enum.Enum):
    outline = "outline"
    points = "points"
    svg = "svg"
    pptx = "pptx"


class GenerationMode(str, enum.Enum):
    knowledge_base = "knowledge_base"
    general = "general"


class GenerationTask(Base, TimestampMixin):
    __tablename__ = "generation_tasks"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    sample_snapshot_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(GUID()), nullable=False, default=list
    )
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, name="task_status"), nullable=False, default=TaskStatus.queued, index=True
    )
    current_stage: Mapped[TaskStage | None] = mapped_column(
        Enum(TaskStage, name="task_stage"), nullable=True
    )
    queue_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_pptx_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    style_fit_score: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    token_consumed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    queue_deadline_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # General mode fields
    mode: Mapped[GenerationMode] = mapped_column(
        Enum(GenerationMode, name="generation_mode"),
        nullable=False,
        default=GenerationMode.knowledge_base,
    )
    visual_style: Mapped[str | None] = mapped_column(String(64), nullable=True)
    communication_mode: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_file_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(GUID()), nullable=False, default=list
    )

    owner = relationship("User", back_populates="generation_tasks")
    trace_stages = relationship(
        "TraceStage",
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="TraceStage.stage_order",
    )

    __table_args__ = (
        Index("idx_tasks_owner_status_recent", "owner_id", "status", "created_at"),
        Index(
            "idx_tasks_queue",
            "status",
            "queue_position",
            postgresql_where=(func.coalesce(status) == "queued"),
        ),
    )
