"""ApiKey ORM model — multi-key rotation per data-model.md §1a."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ARRAY, CheckConstraint, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.models.base import GUID, Base, TimestampMixin


class ApiKey(Base, TimestampMixin):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    key_prefix: Mapped[str] = mapped_column(String(8), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)), nullable=False, default=lambda: ["generation:write"]
    )
    rate_limit_per_min: Mapped[int] = mapped_column(default=60, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    owner = relationship("User", back_populates="api_keys")

    __table_args__ = (
        CheckConstraint("char_length(key_prefix) = 8", name="api_key_prefix_chk"),
        CheckConstraint(
            "rate_limit_per_min > 0 AND rate_limit_per_min <= 1000", name="api_key_rate_chk"
        ),
        Index(
            "idx_api_keys_owner_active",
            "owner_id",
            postgresql_where=func.coalesce(revoked_at) == None,
        ),  # noqa: E711
    )

    def __repr__(self) -> str:
        return f"<ApiKey id={self.id} prefix={self.key_prefix} scopes={self.scopes}>"
