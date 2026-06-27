"""Sample ORM model per data-model.md §2."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.models.base import GUID, Base, TimestampMixin


class FileType(str, enum.Enum):
    pptx = "pptx"
    pdf = "pdf"
    docx = "docx"


class ParseStatus(str, enum.Enum):
    pending = "pending"
    parsing = "parsing"
    parsed = "parsed"
    failed = "failed"


class Sample(Base, TimestampMixin):
    __tablename__ = "samples"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    file_type: Mapped[FileType] = mapped_column(Enum(FileType, name="file_type"), nullable=False)
    raw_path: Mapped[str] = mapped_column(String(512), nullable=False)  # MinIO path
    parse_status: Mapped[ParseStatus] = mapped_column(
        Enum(ParseStatus, name="parse_status"),
        nullable=False,
        default=ParseStatus.pending,
        index=True,
    )
    parse_page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pii_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── relationships ──
    owner = relationship("User", back_populates="samples")
    parse_result = relationship(
        "ParseResult",
        back_populates="sample",
        uselist=False,
        cascade="all, delete-orphan",
    )
    embeddings = relationship("Embedding", back_populates="sample", cascade="all, delete-orphan")
    slide_assets = relationship("SlideAsset", back_populates="source_sample")

    __table_args__ = (
        UniqueConstraint("owner_id", "file_hash", name="uq_samples_owner_hash"),
        Index("idx_samples_owner_active", "owner_id", "deleted_at"),
        Index("idx_samples_parse_status", "parse_status"),
        CheckConstraint("char_length(file_hash) = 64", name="samples_hash_sha256_chk"),
    )

    def __repr__(self) -> str:
        return f"<Sample id={self.id} name={self.file_name} status={self.parse_status}>"
