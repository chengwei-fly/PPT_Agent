"""Standalone worker that polls the Redis generation stream and processes tasks.

Usage:
    uv run python -m src.scheduler.run_worker
"""

from __future__ import annotations

import asyncio
import signal
import sys

from src.core.config import settings
from src.core.observability import get_logger
from src.db.session import dispose_db, init_db
from src.scheduler.queue import (
    acquire_user_slot,
    dequeue_generation_task,
    init_redis,
    release_user_slot,
    shutdown_redis,
)
from src.scheduler.worker import process_generation_task

logger = get_logger("worker.main")

SHUTDOWN_FLAG = False


def _handle_signal(signum: int, frame: object) -> None:
    global SHUTDOWN_FLAG
    logger.info("worker_shutdown_signal", signal=signum)
    SHUTDOWN_FLAG = True


async def run_worker_loop() -> None:
    """Continuously poll the generation stream and process tasks."""
    await init_db()
    await init_redis()

    logger.info("worker_started", stream="stream:generation:tasks")

    while not SHUTDOWN_FLAG:
        try:
            entry = await dequeue_generation_task(timeout_ms=2000)
            if entry is None:
                continue

            task_id = entry["task_id"]
            owner_id = entry["owner_id"]
            logger.info("worker_picked_task", task_id=task_id)

            # Check cancel marker
            from src.scheduler.queue import get_client

            client = get_client()
            cancelled = await client.get(f"cancel:{task_id}")
            if cancelled:
                logger.info("worker_task_cancelled", task_id=task_id)
                continue

            if not await acquire_user_slot(owner_id, limit=settings.user_concurrency_limit):
                logger.info("worker_slot_full", owner_id=owner_id, task_id=task_id)
                continue

            try:
                await process_generation_task(task_id, owner_id)
            finally:
                await release_user_slot(owner_id)

        except Exception:
            logger.exception("worker_loop_error")

    await shutdown_redis()
    await dispose_db()
    logger.info("worker_stopped")


def main() -> None:
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    try:
        asyncio.run(run_worker_loop())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
