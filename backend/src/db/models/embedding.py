"""Embedding ORM model (pgvector) per data-model.md §4."""

from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.config import settings
from src.db.models.base import GUID, Base


class Embedding(Base):
    __tablename__ = "embeddings"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    sample_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("samples.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)  # PII-redacted
    vector = mapped_column(Vector(settings.embedding_dimension), nullable=False)
    model_name: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    sample = relationship("Sample", back_populates="embeddings")

    __table_args__ = (
        UniqueConstraint("sample_id", "chunk_index", name="uq_embeddings_sample_chunk"),
        CheckConstraint("chunk_index >= 0", name="embeddings_chunk_index_nonneg"),
    )
