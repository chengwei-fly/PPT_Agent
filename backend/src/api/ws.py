"""WebSocket channel per contracts/events.yaml (T046).

Channels:
- `task:{task_id}` — per-task progress events
- `user:{user_id}:materials` — material index events
- `draft:{draft_id}` — draft lock/save/export events
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from src.core.config import settings
from src.core.observability import get_logger
from src.core.security import hash_api_key
from src.db.models import User
from src.db.session import get_session_factory
from src.scheduler.queue import subscribe_ws

router = APIRouter()
logger = get_logger("ws")

CONNECTION_REGISTRY: dict[str, set[WebSocket]] = {}


async def _authenticate_ws(websocket: WebSocket, token: str | None) -> str | None:
    """Resolve token from query string or first subprotocol. Returns user_id or None."""
    if not token:
        token = websocket.query_params.get("token")
    if not token:
        return None
    if token == settings.dev_api_key:
        return "dev"
    key_hash = hash_api_key(token)
    factory = get_session_factory()
    async with factory() as session:
        from sqlalchemy import select

        from src.db.models import ApiKey

        result = await session.execute(
            select(ApiKey, User)
            .join(User, ApiKey.owner_id == User.id)
            .where(ApiKey.key_hash == key_hash, ApiKey.revoked_at.is_(None))
        )
        row = result.first()
        if not row:
            return None
        api_key, user = row
        return str(user.id)


async def _authorize_channel(channel: str, user_id: str) -> bool:
    """Check that the authenticated user has access to the given channel."""
    parts = channel.split(":")
    if len(parts) < 2:
        return False

    channel_type = parts[0]

    # user:{user_id}:materials — must match authenticated user
    if channel_type == "user" and len(parts) >= 2:
        return parts[1] == user_id

    # task:{task_id} — check task ownership
    if channel_type == "task":
        try:
            task_uuid = uuid.UUID(parts[1])
        except ValueError:
            return False
        factory = get_session_factory()
        async with factory() as session:
            from sqlalchemy import select

            from src.db.models import GenerationTask

            result = await session.execute(
                select(GenerationTask.owner_id).where(GenerationTask.id == task_uuid)
            )
            row = result.scalar_one_or_none()
            return row is not None and str(row) == user_id

    # draft:{draft_id} — check draft ownership
    if channel_type == "draft":
        try:
            draft_uuid = uuid.UUID(parts[1])
        except ValueError:
            return False
        factory = get_session_factory()
        async with factory() as session:
            from sqlalchemy import select

            from src.db.models import Draft

            result = await session.execute(select(Draft.owner_id).where(Draft.id == draft_uuid))
            row = result.scalar_one_or_none()
            return row is not None and str(row) == user_id

    return False


@router.websocket("/")
async def ws_endpoint(
    websocket: WebSocket,
    channel: str = Query(..., description="e.g. task:UUID, user:UUID:materials, draft:UUID"),
    token: str | None = Query(None),
) -> None:
    await websocket.accept()
    user_id = await _authenticate_ws(websocket, token)
    if not user_id:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Dev user bypasses channel authorization
    if user_id != "dev" and not await _authorize_channel(channel, user_id):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Per-channel connection registry
    conn_set = CONNECTION_REGISTRY.setdefault(channel, set())
    conn_set.add(websocket)
    connection_id = uuid.uuid4().hex
    logger.info("ws_connected", channel=channel, user_id=user_id, connection_id=connection_id)

    try:
        # Send hello
        await websocket.send_json(
            {"type": "hello", "channel": channel, "connection_id": connection_id}
        )

        # Start pub/sub listener task
        listener_task = asyncio.create_task(_relay_events(websocket, channel))

        # Read loop (heartbeat / client commands)
        while True:
            msg = await websocket.receive_text()
            try:
                data = json.loads(msg)
            except json.JSONDecodeError:
                data = {"type": "ping", "raw": msg}
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong", "ts": data.get("ts")})
    except WebSocketDisconnect:
        pass
    finally:
        conn_set.discard(websocket)
        listener_task.cancel()
        logger.info("ws_disconnected", channel=channel, connection_id=connection_id)


async def _relay_events(websocket: WebSocket, channel: str) -> None:
    """Forward Redis pub/sub events to the connected WebSocket."""
    try:
        async for event in subscribe_ws(channel):
            await websocket.send_json(event)
    except asyncio.CancelledError:
        pass
    except Exception as e:  # pragma: no cover
        logger.warning(f"ws_relay_error: {e}")


async def broadcast(channel: str, event: dict[str, Any]) -> None:
    """Direct (in-process) broadcast — used by services that already have a session."""
    conns = CONNECTION_REGISTRY.get(channel, set())
    dead: list[WebSocket] = []
    for ws in conns:
        try:
            await ws.send_json(event)
        except Exception:
            dead.append(ws)
    for ws in dead:
        conns.discard(ws)
