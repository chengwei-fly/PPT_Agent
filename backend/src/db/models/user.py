"""User ORM model per data-model.md §1."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import ARRAY, DateTime, Enum, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.models.base import GUID, Base, TimestampMixin


class UserTier(str, enum.Enum):
    personal = "personal"
    team = "team"
    enterprise = "enterprise"


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(64), nullable=False)
    tier: Mapped[UserTier] = mapped_column(
        Enum(UserTier, name="user_tier"), nullable=False, default=UserTier.personal
    )
    active_sample_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(GUID()), nullable=False, default=list
    )
    # NOTE: api_key_hash is legacy — prefer api_keys table (T016a)
    api_key_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── relationships ──
    api_keys = relationship("ApiKey", back_populates="owner", cascade="all, delete-orphan")
    samples = relationship("Sample", back_populates="owner", cascade="all, delete-orphan")
    preferences = relationship("Preference", back_populates="owner", cascade="all, delete-orphan")
    generation_tasks = relationship(
        "GenerationTask", back_populates="owner", cascade="all, delete-orphan"
    )
    drafts = relationship("Draft", back_populates="owner", cascade="all, delete-orphan")

    __table_args__ = (
        Index(
            "idx_users_email_active", "email", postgresql_where=(func.coalesce(deleted_at) == None)
        ),  # noqa: E711
        Index("idx_users_tier", "tier"),
        Index("idx_users_deleted_at", "deleted_at"),
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email} tier={self.tier}>"
