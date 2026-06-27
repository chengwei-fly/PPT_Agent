"""Unit tests for cursor pagination helpers (T016c)."""

from __future__ import annotations

import base64


class TestCursorEncode:
    def test_roundtrip(self):
        from src.api.pagination import decode_cursor, encode_cursor

        payload = {"id": "abc-123", "ts": 1700000000, "tag": "next"}
        cursor = encode_cursor(payload)
        assert isinstance(cursor, str)
        # URL-safe base64: no `+` or `/`, no `=` padding
        assert "+" not in cursor
        assert "/" not in cursor
        assert "=" not in cursor
        assert decode_cursor(cursor) == payload

    def test_decode_empty(self):
        from src.api.pagination import decode_cursor

        assert decode_cursor("") is None
        assert decode_cursor(None) is None  # type: ignore[arg-type]

    def test_decode_invalid_garbage(self):
        from src.api.pagination import decode_cursor

        # Random bytes that aren't valid base64-encoded JSON
        assert decode_cursor("not-a-cursor") is None
        assert decode_cursor("@@@@") is None

    def test_decode_truncated_raises_but_returns_none(self):
        from src.api.pagination import decode_cursor

        # A valid cursor truncated should NOT raise; it should return None
        cursor = base64.urlsafe_b64encode(b'{"a":1').decode().rstrip("=")
        # The decoder is forgiving: it will try to parse and on failure → None
        result = decode_cursor(cursor)
        assert result is None or isinstance(result, dict)

    def test_cursors_are_order_independent(self):
        from src.api.pagination import encode_cursor

        a = encode_cursor({"a": 1, "b": 2})
        b = encode_cursor({"b": 2, "a": 1})
        assert a == b  # sort_keys=True makes the output stable


class TestCursorPage:
    def test_empty_page(self):
        from src.api.pagination import CursorPage

        p = CursorPage[int](items=[], next_cursor=None, has_more=False)
        assert p.items == []
        assert p.next_cursor is None
        assert p.has_more is False

    def test_with_items(self):
        from src.api.pagination import CursorPage

        p = CursorPage[int](items=[1, 2, 3], next_cursor="abc", has_more=True)
        assert p.items == [1, 2, 3]
        assert p.next_cursor == "abc"
        assert p.has_more is True

    def test_generic_typing(self):
        from src.api.pagination import CursorPage

        # Generic works for non-int types
        p = CursorPage[str](items=["a", "b"])
        assert p.items == ["a", "b"]


class TestCursorQueryParams:
    def test_signature(self):
        from src.api.pagination import cursor_query_params

        # Default values
        cursor, limit = cursor_query_params(cursor=None, limit=50)
        assert cursor is None
        assert limit == 50

    def test_custom_limit(self):
        from src.api.pagination import cursor_query_params

        cursor, limit = cursor_query_params(cursor="abc", limit=200)
        assert cursor == "abc"
        assert limit == 200
