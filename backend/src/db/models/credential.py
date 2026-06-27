"""Credential ORM model — stores AgentScope provider credentials per user."""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.db.models.base import GUID, Base, TimestampMixin


class Credential(Base, TimestampMixin):
    __tablename__ = "credentials"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="AgentScope credential type discriminator, e.g. 'openai_credential'",
    )
    name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default="",
        comment="User-facing display name",
    )
    credential_data: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Serialized credential (api_key stored as SecretStr)",
    )
    is_default: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment="Whether this is the default credential for its provider type",
    )

    __table_args__ = (
        Index(
            "idx_credentials_owner_provider",
            "owner_id",
            "provider_type",
            postgresql_where=func.coalesce(is_default) == True,  # noqa: E712
        ),
    )
