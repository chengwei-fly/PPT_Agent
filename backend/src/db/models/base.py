"""Shared SQLAlchemy types / mixins used by all ORM models."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import CHAR, DateTime, TypeDecorator, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

# Re-export Base from session so models can import from here
from src.db.session import Base  # noqa: F401


class GUID(TypeDecorator):
    """Cross-dialect UUID column.

    Uses native UUID on PostgreSQL, CHAR(36) elsewhere.
    """

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):  # type: ignore[override]
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):  # type: ignore[override]
        if value is None:
            return None
        if not isinstance(value, uuid.UUID):
            value = uuid.UUID(str(value))
        if dialect.name == "postgresql":
            return value
        return str(value)

    def process_result_value(self, value, dialect):  # type: ignore[override]
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(str(value))


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()


def utc_now() -> datetime:
    return datetime.utcnow()


# ─── Enum helpers ───────────────────────────────────────────────────
class StrEnum(str, enum.Enum):
    """String-based enum that works well with SQLAlchemy + Pydantic."""

    def __str__(self) -> str:
        return str(self.value)


# ─── Timestamp mixin ────────────────────────────────────────────────
class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=utc_now, nullable=False
    )
