"""SecurityEvent ORM model per data-model.md §8."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.db.models.base import GUID, Base


class SecurityEventType(str, enum.Enum):
    pii_hit = "pii_hit"
    pii_blocked = "pii_blocked"
    pii_replaced = "pii_replaced"
    pii_acknowledged = "pii_acknowledged"
    unauth_access = "unauth_access"
    bulk_export = "bulk_export"
    bulk_delete = "bulk_delete"


class SecurityAction(str, enum.Enum):
    replace = "replace"
    block = "block"
    allow = "allow"


class SecurityEvent(Base):
    __tablename__ = "security_events"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[SecurityEventType] = mapped_column(
        Enum(SecurityEventType, name="security_event_type"), nullable=False, index=True
    )
    hit_field: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action_taken: Mapped[SecurityAction] = mapped_column(
        Enum(SecurityAction, name="security_action"), nullable=False
    )
    related_resource_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index("idx_security_owner_recent", "owner_id", "created_at"),
        Index("idx_security_type_recent", "event_type", "created_at"),
    )
