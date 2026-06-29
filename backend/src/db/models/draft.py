"""Draft / DraftSlide / MaterialSearchIndex ORM models — US6."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.models.base import GUID, Base, TimestampMixin


class DraftStatus(str, enum.Enum):
    active = "active"
    archived = "archived"
    exported = "exported"


class DraftSlideSourceType(str, enum.Enum):
    reused = "reused"
    generated = "generated"
    manual = "manual"


class Draft(Base, TimestampMixin):
    __tablename__ = "drafts"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[DraftStatus] = mapped_column(
        Enum(DraftStatus, name="draft_status"), nullable=False, default=DraftStatus.active
    )
    overall_style: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    last_saved_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    editor_user_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    lock_acquired_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    lock_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    owner = relationship("User", back_populates="drafts")
    slides = relationship(
        "DraftSlide",
        back_populates="draft",
        cascade="all, delete-orphan",
        order_by="DraftSlide.slide_order",
    )
    export_jobs = relationship(
        "DraftExportJob", back_populates="draft", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_drafts_owner_status", "owner_id", "status"),
        Index(
            "idx_drafts_lock_expiry",
            "lock_expires_at",
            postgresql_where=(func.coalesce(lock_expires_at) != None),  # noqa: E711
        ),
    )


class DraftSlide(Base):
    __tablename__ = "draft_slides"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    draft_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("drafts.id", ondelete="CASCADE"), nullable=False
    )
    slide_order: Mapped[int] = mapped_column(Integer, nullable=False)
    source_type: Mapped[DraftSlideSourceType] = mapped_column(
        Enum(DraftSlideSourceType, name="draft_slide_source_type"), nullable=False
    )
    # For reused slides → SlideAsset.id; for generated → TraceStage.id
    material_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("slide_assets.id", ondelete="SET NULL"), nullable=True
    )
    generated_stage_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("trace_stages.id", ondelete="SET NULL"), nullable=True
    )
    # Snapshot of the rendered slide (SVG) — fully editable independent of origin
    materialized_svg: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    style_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    draft = relationship("Draft", back_populates="slides")
    material = relationship("SlideAsset", back_populates="draft_slides")

    __table_args__ = (
        UniqueConstraint("draft_id", "slide_order", name="uq_draft_slides_order"),
        CheckConstraint("slide_order >= 0", name="draft_slides_order_nonneg"),
    )


class MaterialSearchIndex(Base):
    """Pre-computed search index for material_library.

    Maintained by trigger trg_slide_assets_sync_search on slide_assets.
    Holds BM25 token + tsvector + metadata for fast hybrid search (R9).
    """

    __tablename__ = "material_search_index"

    asset_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("slide_assets.id", ondelete="CASCADE"),
        primary_key=True,
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    visual_type: Mapped[str] = mapped_column(String(32), nullable=False)
    industry_tags: Mapped[list[str]] = mapped_column(
        ARRAY(String(32)), nullable=False, default=list
    )
    source_sample_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    search_tsv = mapped_column(TSVECTOR, nullable=True)
    indexed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_material_search_tsv", "search_tsv", postgresql_using="gin"),
        Index("idx_material_search_visual", "visual_type"),
    )


class DraftExportJob(Base, TimestampMixin):
    """Tracks async PPTX export jobs for drafts (FR-036)."""

    __tablename__ = "draft_export_jobs"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    draft_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("drafts.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    pptx_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    draft = relationship("Draft", back_populates="export_jobs")
