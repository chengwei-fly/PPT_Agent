"""Global test fixtures and configuration."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from typing import Any

# Ensure tests use the test database unless explicitly overridden
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://pptagent:pptagent@localhost:5432/pptagent_test"
)
os.environ.setdefault(
    "DATABASE_URL_SYNC", "postgresql://pptagent:pptagent@localhost:5432/pptagent_test"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")  # Use DB 1 for tests
os.environ.setdefault("S3_ENDPOINT", "localhost:9000")
os.environ.setdefault("S3_ACCESS_KEY", "minioadmin")
os.environ.setdefault("S3_SECRET_KEY", "minioadmin")
os.environ.setdefault("S3_BUCKET_HOT", "ppt-hot-test")
os.environ.setdefault("S3_BUCKET_COLD", "ppt-cold-test")
os.environ.setdefault("OPENAI_API_KEY", "test-key-not-used")
os.environ.setdefault("DEV_API_KEY", "test-key")
os.environ.setdefault("DEV_USER_EMAIL", "test@pptagent.local")
os.environ.setdefault("SECRET_KEY", "test-secret-key-min-32-chars-long-for-jwt")

import pytest
import pytest_asyncio


@pytest.fixture(scope="session")
def event_loop() -> Iterator[asyncio.AbstractEventLoop]:
    """Session-scoped event loop for async fixtures."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def dev_api_key() -> str:
    return os.environ["DEV_API_KEY"]


@pytest.fixture
def dev_user_email() -> str:
    return os.environ["DEV_USER_EMAIL"]


@pytest.fixture
def auth_headers(dev_api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {dev_api_key}"}


@pytest_asyncio.fixture
async def async_client() -> AsyncIterator[Any]:
    """Async HTTP client for FastAPI app."""
    from httpx import ASGITransport, AsyncClient

    from src.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[Any]:
    """Async database session for tests."""

    from src.db.session import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        yield session
        await session.rollback()
