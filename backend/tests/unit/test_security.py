"""Unit tests for security helpers (T017)."""

from __future__ import annotations

import pytest


class TestHashApiKey:
    def test_sha256_hex_64(self):
        from src.core.security import hash_api_key

        h = hash_api_key("dev-key")
        assert len(h) == 64
        # Deterministic
        assert hash_api_key("dev-key") == h
        # Different input → different hash
        assert hash_api_key("other-key") != h

    def test_unicode_keys(self):
        from src.core.security import hash_api_key

        # Should not raise on non-ASCII bytes
        h = hash_api_key("key-密码-🔑")
        assert len(h) == 64


class TestGetApiKeyFromHeader:
    @pytest.mark.asyncio
    async def test_bearer(self):
        from src.core.security import get_api_key_from_header

        out = await get_api_key_from_header(authorization="Bearer dev-key", x_api_key=None)
        assert out == "dev-key"

    @pytest.mark.asyncio
    async def test_x_api_key_fallback(self):
        from src.core.security import get_api_key_from_header

        out = await get_api_key_from_header(authorization=None, x_api_key="x-key-123")
        assert out == "x-key-123"

    @pytest.mark.asyncio
    async def test_bearer_takes_precedence(self):
        from src.core.security import get_api_key_from_header

        out = await get_api_key_from_header(authorization="Bearer real", x_api_key="x-key")
        assert out == "real"

    @pytest.mark.asyncio
    async def test_missing_raises(self):
        from src.core.errors import UnauthorizedError
        from src.core.security import get_api_key_from_header

        with pytest.raises(UnauthorizedError):
            await get_api_key_from_header(authorization=None, x_api_key=None)

    @pytest.mark.asyncio
    async def test_authorization_without_bearer_prefix(self):
        from src.core.errors import UnauthorizedError
        from src.core.security import get_api_key_from_header

        with pytest.raises(UnauthorizedError):
            await get_api_key_from_header(authorization="Basic abc==", x_api_key=None)


class TestRequireScope:
    def test_returns_checker_callable(self):
        from src.core.security import require_scope

        checker = require_scope("generation:write", "knowledge:write")
        assert callable(checker)
