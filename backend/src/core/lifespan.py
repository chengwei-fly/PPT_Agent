"""FastAPI startup/shutdown hooks."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from src.core.config import settings
from src.core.observability import shutdown_observability
from src.db.session import dispose_db, init_db
from src.scheduler.queue import init_redis
from src.storage.minio import init_minio

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(settings.log_namespace)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and tear down application resources."""
    logger.info("startup", extra={"version": settings.app_version, "env": settings.app_env})

    # Database
    await init_db()

    # Redis
    await init_redis()

    # MinIO
    init_minio()

    # AgentScope event bus
    try:
        from src.agents.base import init_agent_bus

        await init_agent_bus()
    except Exception as e:  # pragma: no cover
        logger.warning(f"agent bus init failed (non-fatal): {e}")

    yield

    logger.info("shutdown")
    await dispose_db()
    await shutdown_observability()
