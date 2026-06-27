"""Cursor pagination helper (T016c).

Used for /security/events (large table) and stream-friendly endpoints.
"""

from __future__ import annotations

import base64
import json
from typing import Any, Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel

T = TypeVar("T")


def encode_cursor(payload: dict[str, Any]) -> str:
    """Encode a dict as a URL-safe base64 cursor."""
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str) -> dict[str, Any] | None:
    """Decode a base64 cursor back to a dict. Returns None on invalid input."""
    if not cursor:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None


class CursorPage(BaseModel, Generic[T]):
    items: list[T]
    next_cursor: str | None = None
    has_more: bool = False


def cursor_query_params(
    cursor: str | None = Query(None, description="Opaque pagination cursor"),
    limit: int = Query(50, ge=1, le=200, description="Page size"),
) -> tuple[str | None, int]:
    """Common pagination query params."""
    return cursor, limit
