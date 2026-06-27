"""Pydantic v2 DTO base classes (T027) + OpenAPI metadata."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class BaseDTO(BaseModel):
    """Base Pydantic v2 DTO.

    - `from_attributes=True` allows ORM mode (create from SQLAlchemy models)
    - `populate_by_name=True` allows alias and field name interchangeably
    - `extra="forbid"` makes API contracts strict
    """

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        extra="forbid",
        str_strip_whitespace=True,
    )


class TimestampedDTO(BaseDTO):
    created_at: datetime
    updated_at: datetime | None = None


class IdDTO(BaseDTO):
    id: str = Field(..., description="Resource UUID")


class PageMeta(BaseModel):
    """Pagination metadata (cursor-based per T016c)."""

    model_config = ConfigDict(extra="forbid")

    total: int | None = Field(None, description="Total count, may be None for cursor pagination")
    next_cursor: str | None = Field(None, description="Cursor for the next page (opaque)")
    has_more: bool = Field(False, description="Whether more pages exist")


class Page(BaseDTO):
    """Generic paginated response envelope."""

    items: list[Any] = Field(default_factory=list)
    meta: PageMeta = Field(default_factory=PageMeta)


class ErrorDetail(BaseDTO):
    """RFC 7807 error details."""

    code: str = Field(..., description="Stable error code, e.g. PPTAGENT.PII_HIT")
    message: str
    request_id: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseDTO):
    status: str = "ok"
    version: str
    queue_length: int = 0
    db_ok: bool = True
    redis_ok: bool = True
    s3_ok: bool = True
