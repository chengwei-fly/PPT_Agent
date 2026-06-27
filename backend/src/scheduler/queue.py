"""Redis client + Stream wrapper (T020).

Used for:
- Task queue (FR-029: FIFO + 5min timeout + per-user 2-concurrency gate)
- Rate limiting (T017: 60 req/min)
- Idempotency cache fallback
- WebSocket pub/sub channel registry
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any

import redis.asyncio as redis

from src.core.config import settings
from src.core.observability import get_logger

logger = get_logger("queue")

_client: redis.Redis | None = None

# ─── Stream keys ────────────────────────────────────────────────────
GENERATION_STREAM = "stream:generation:tasks"
WS_CHANNEL_PREFIX = "ws:"


async def init_redis() -> None:
    global _client
    if _client is not None:
        return
    _client = redis.from_url(
        str(settings.redis_url),
        encoding="utf-8",
        decode_responses=True,
        max_connections=20,
    )
    await _client.ping()
    logger.info("redis_initialized", url=str(settings.redis_url))


async def shutdown_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def get_client() -> redis.Redis:
    if _client is None:
        raise RuntimeError("Redis not initialized — call init_redis() first")
    return _client


# ─── Task queue (FIFO + 5min deadline + per-user concurrency) ──────
async def enqueue_generation_task(task_id: str, owner_id: str) -> int:
    """Add a task to the generation stream, return queue position (1-based)."""
    client = get_client()
    now_ms = int(time.time() * 1000)
    deadline_ms = now_ms + settings.queue_deadline_seconds * 1000
    payload = {
        "task_id": task_id,
        "owner_id": owner_id,
        "enqueued_at": str(now_ms),
        "deadline_ms": str(deadline_ms),
    }
    await client.xadd(GENERATION_STREAM, payload, maxlen=1000, approximate=True)
    # Position = stream length (approximate)
    length = await client.xlen(GENERATION_STREAM)
    return int(length)


async def dequeue_generation_task(timeout_ms: int = 1000) -> dict[str, str] | None:
    """Pop next task (consumer group 'workers'). Returns None on timeout."""
    client = get_client()
    try:
        await client.xgroup_create(GENERATION_STREAM, "workers", id="$", mkstream=True)
    except redis.ResponseError:
        pass  # group exists
    result = await client.xreadgroup(
        "workers", "worker-1", {GENERATION_STREAM: ">"}, count=1, block=timeout_ms
    )
    if not result:
        return None
    _, entries = result[0]
    if not entries:
        return None
    msg_id, data = entries[0]
    await client.xack(GENERATION_STREAM, "workers", msg_id)
    return {"_id": msg_id, **data}


async def remove_from_queue(task_id: str) -> None:
    """Best-effort: remove a queued task by id (cancel)."""
    client = get_client()
    # NOTE: Streams don't support efficient removal — workers should check status on pickup
    await client.set(f"cancel:{task_id}", "1", ex=300)


# ─── Rate limit (T017 / FR-029) ────────────────────────────────────
async def check_rate_limit(user_id: str, limit_per_min: int) -> tuple[bool, int]:
    """Sliding window rate limit. Returns (allowed, retry_after_seconds)."""
    client = get_client()
    bucket = int(time.time() // 60)
    key = f"rl:{user_id}:{bucket}"
    pipe = client.pipeline()
    pipe.incr(key, 1)
    pipe.expire(key, 70)
    results = await pipe.execute()
    count = int(results[0])
    if count > limit_per_min:
        retry_after = 60 - int(time.time() % 60)
        return False, retry_after
    return True, 0


# ─── Per-user concurrency gate (FR-029: ≤2) ────────────────────────
async def acquire_user_slot(user_id: str, limit: int = 2) -> bool:
    client = get_client()
    key = f"slot:{user_id}"
    count = await client.incr(key, 1)
    if count > limit:
        await client.decr(key, 1)
        return False
    await client.expire(key, 1800)
    return True


async def release_user_slot(user_id: str) -> None:
    client = get_client()
    await client.decr(f"slot:{user_id}", 1)


# ─── WS pub/sub ─────────────────────────────────────────────────────
async def publish_ws_event(channel: str, event: dict[str, Any]) -> None:
    client = get_client()
    await client.publish(f"{WS_CHANNEL_PREFIX}{channel}", json.dumps(event, default=str))


async def subscribe_ws(channel: str) -> AsyncIterator[dict[str, Any]]:
    client = get_client()
    pubsub = client.pubsub()
    await pubsub.subscribe(f"{WS_CHANNEL_PREFIX}{channel}")
    try:
        async for msg in pubsub.listen():
            if msg["type"] == "message":
                try:
                    yield json.loads(msg["data"])
                except json.JSONDecodeError:
                    continue
    finally:
        await pubsub.unsubscribe(f"{WS_CHANNEL_PREFIX}{channel}")
        await pubsub.aclose()
