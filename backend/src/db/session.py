"""SQLAlchemy 2.x async session management + Alembic env integration."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from src.core.config import settings

logger = logging.getLogger(settings.log_namespace)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""

    type_annotation_map: dict[Any, Any] = {}


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


async def init_db() -> None:
    """Initialize the async engine and session factory."""
    global _engine, _session_factory
    if _engine is not None:
        return
    _engine = create_async_engine(
        settings.database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout,
        echo=settings.db_echo,
        future=True,
        # PostgreSQL-specific: enable pgvector type coercion
        connect_args={"server_settings": {"application_name": settings.app_name}},
    )
    _session_factory = async_sessionmaker(
        bind=_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    logger.info("db_initialized", pool_size=settings.db_pool_size)


async def dispose_db() -> None:
    """Dispose of the async engine on shutdown."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError("Database not initialized — call init_db() first")
    return _session_factory


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency — yields a session with auto-rollback on error."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        else:
            await session.commit()


def get_engine() -> AsyncEngine:
    if _engine is None:
        raise RuntimeError("Database not initialized — call init_db() first")
    return _engine
