"""ParseResult ORM model per data-model.md §3."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.models.base import GUID, Base


class ParseResult(Base):
    __tablename__ = "parse_results"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    sample_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("samples.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    structure_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    parse_version: Mapped[str] = mapped_column(String(16), nullable=False)
    parse_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    parse_finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    sample = relationship("Sample", back_populates="parse_result")

    def __repr__(self) -> str:
        return f"<ParseResult sample_id={self.sample_id} version={self.parse_version}>"
