"""Preference ORM model per data-model.md §5."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.models.base import GUID, Base, TimestampMixin


class PreferenceScope(str, enum.Enum):
    cover = "cover"
    toc = "toc"
    body = "body"
    closing = "closing"
    all = "all"


class Preference(Base, TimestampMixin):
    __tablename__ = "preferences"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)  # e.g. "P-007"
    owner_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    source_chains: Mapped[dict] = mapped_column(JSONB, nullable=False)  # FR source chain
    rule_text: Mapped[str] = mapped_column(Text, nullable=False)
    applies_to: Mapped[PreferenceScope] = mapped_column(
        Enum(PreferenceScope, name="preference_scope"), nullable=False
    )
    apply_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ignore_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    owner = relationship("User", back_populates="preferences")

    __table_args__ = (
        Index("idx_preferences_owner_active", "owner_id", "is_active"),
        Index("idx_preferences_owner_recent", "owner_id", "last_applied_at"),
    )
