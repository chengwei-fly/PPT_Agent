"""SlideAsset ORM model — US6: 按页为单位的素材资产 per data-model.md §2.2.10."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import ARRAY, DateTime, Enum, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.models.base import GUID, Base


class SlideVisualType(str, enum.Enum):
    cover = "cover"
    toc = "toc"
    architecture = "architecture"
    flowchart = "flowchart"
    data = "data"
    body = "body"
    closing = "closing"
    mixed = "mixed"


class SlideAsset(Base):
    """A single reusable slide extracted from a sample.

    R12 / Invariant 7: source_sample_id is NULLable — orphaning allowed,
    not cascading delete.
    """

    __tablename__ = "slide_assets"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    source_sample_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("samples.id", ondelete="SET NULL"), nullable=True, index=True
    )
    page_index: Mapped[int] = mapped_column(Integer, nullable=False)
    visual_type: Mapped[SlideVisualType] = mapped_column(
        Enum(SlideVisualType, name="slide_visual_type"), nullable=False, index=True
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    svg_payload: Mapped[str | None] = mapped_column(Text, nullable=True)  # SVG source
    thumbnail_path: Mapped[str | None] = mapped_column(String(512), nullable=True)  # MinIO
    color_palette: Mapped[list[str]] = mapped_column(
        ARRAY(String(16)), nullable=False, default=list
    )
    font_family: Mapped[str | None] = mapped_column(String(64), nullable=True)
    industry_tags: Mapped[list[str]] = mapped_column(
        ARRAY(String(32)), nullable=False, default=list
    )
    embedding = mapped_column(
        "embedding",  # column name
        # actual Vector is created in 0007 migration; here we use JSONB fallback for ORM compat
        JSONB,
        nullable=True,
    )
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    source_sample = relationship("Sample", back_populates="slide_assets")
    draft_slides = relationship("DraftSlide", back_populates="material")

    __table_args__ = (
        Index("idx_slide_assets_visual_type", "visual_type"),
        Index("idx_slide_assets_industry", "industry_tags", postgresql_using="gin"),
        Index(
            "idx_slide_assets_source",
            "source_sample_id",
            postgresql_where=func.coalesce(source_sample_id) != None,
        ),  # noqa: E711
    )
