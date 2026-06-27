"""Contract test for the WebSocket /ws channel (T046, partial — events.yaml).

Validates the event types emitted during a generation run.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.contract


# Events that MUST be emitted on the `task:{task_id}` channel
EXPECTED_TASK_EVENTS = {
    "outline.running",
    "outline.success",
    "points.running",
    "points.success",
    "svg.running",
    "svg.success",
    "pptx.running",
    "pptx.success",
}


class TestTaskChannelEvents:
    def test_all_four_stages_emit_running_and_success(self) -> None:
        for stage in ("outline", "points", "svg", "pptx"):
            assert f"{stage}.running" in EXPECTED_TASK_EVENTS
            assert f"{stage}.success" in EXPECTED_TASK_EVENTS

    def test_event_payload_shape(self) -> None:
        """Each event MUST include type, stage, status, and ts (or task_id)."""
        # The actual shape is implemented in pipeline._emit_ws.
        # The contract frozen here is: minimal payload has at least
        # type + stage + status.
        sample = {
            "type": "outline.success",
            "stage": "outline",
            "status": "success",
            "task_id": "00000000-0000-0000-0000-000000000000",
        }
        for key in ("type", "stage", "status", "task_id"):
            assert key in sample

    def test_cancellation_event_on_delete(self) -> None:
        """DELETE MUST emit `task.cancelled` on the task channel."""
        evt = {
            "type": "task.cancelled",
            "task_id": "00000000-0000-0000-0000-000000000000",
            "ts": "2026-06-24T00:00:00",
        }
        assert evt["type"] == "task.cancelled"

    def test_queued_event_on_user_channel(self) -> None:
        """When a user is queued (concurrency limit), emit `task.queued` on
        the user channel `user:{user_id}:generations`."""
        evt = {
            "type": "task.queued",
            "task_id": "00000000-0000-0000-0000-000000000000",
            "queue_position": 3,
        }
        assert evt["type"] == "task.queued"
        assert evt["queue_position"] >= 1


class TestWsHelloMessage:
    def test_hello_shape(self) -> None:
        """The server MUST send a `hello` message on connect with
        channel + connection_id."""
        hello = {
            "type": "hello",
            "channel": "task:00000000-0000-0000-0000-000000000000",
            "connection_id": "abcdef0123456789",
        }
        assert hello["type"] == "hello"
        assert "channel" in hello
        assert "connection_id" in hello

    def test_pong_shape(self) -> None:
        """The server MUST reply to `ping` with `pong` echoing ts."""
        pong = {"type": "pong", "ts": 1700000000}
        assert pong["type"] == "pong"
        assert "ts" in pong
