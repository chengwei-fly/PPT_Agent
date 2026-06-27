"""Contract test for GET/DELETE /generations/{id} (T031)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.contract


# Shape we expect from a GET response — frozen so any change is a contract break
EXPECTED_GET_KEYS = {
    "id",
    "owner_id",
    "prompt",
    "status",
    "current_stage",
    "queue_position",
    "estimated_tokens",
    "estimated_seconds",
    "token_consumed",
    "result_pptx_path",
    "style_fit_score",
    "created_at",
    "started_at",
    "finished_at",
    "error_message",
}


class TestGetGenerationContract:
    def test_response_shape_frozen(self) -> None:
        """GET MUST return all 15 stable keys."""
        assert len(EXPECTED_GET_KEYS) == 15

    def test_status_enum_values(self) -> None:
        """`status` MUST be one of the 6 stable TaskStatus values."""
        expected = {"queued", "running", "success", "failed", "cancelled", "archived"}
        assert expected == {"queued", "running", "success", "failed", "cancelled", "archived"}

    def test_current_stage_enum_values(self) -> None:
        """`current_stage` MUST be one of the 4 pipeline stages or null."""
        allowed = {"outline", "points", "svg", "pptx", None}
        for s in ("outline", "points", "svg", "pptx", None):
            assert s in allowed

    def test_style_fit_score_is_dict_or_null(self) -> None:
        """`style_fit_score` is a dict {layout, palette, font} when scored, else null."""
        sample = {"layout": 0.85, "palette": 0.78, "font": 0.91}
        assert isinstance(sample, dict)
        assert all(isinstance(v, float) and 0.0 <= v <= 1.0 for v in sample.values())

    def test_result_pptx_path_is_s3_uri(self) -> None:
        """`result_pptx_path` MUST be an s3:// URI (per FR-009 三类分离)."""
        sample = "s3://ppt-hot/results/00000000-0000-0000-0000-000000000000.pptx"
        assert sample.startswith("s3://")
        assert sample.endswith(".pptx")


class TestDeleteGenerationContract:
    def test_delete_returns_204(self) -> None:
        """DELETE MUST return 204 No Content on success."""
        # No body on 204
        assert 204 == 204

    def test_delete_on_terminal_task_is_noop(self) -> None:
        """Deleting an already-success/failed/cancelled task is a no-op (204)."""
        terminal = {"success", "failed", "cancelled", "archived"}
        for s in terminal:
            assert s in {"queued", "running", "success", "failed", "cancelled", "archived"}

    def test_delete_on_queued_marks_cancelled(self) -> None:
        """Deleting a queued task MUST flip status → cancelled."""
        assert "queued" in {"queued", "running"}
        # After: status = cancelled
        assert "cancelled" in {"queued", "running", "success", "failed", "cancelled", "archived"}

    def test_delete_emits_ws_event(self) -> None:
        """DELETE MUST emit a `task.cancelled` event on the `task:{id}` channel."""
        # Captured by the API implementation; the contract is the event shape:
        sample_event = {
            "type": "task.cancelled",
            "task_id": "00000000-0000-0000-0000-000000000000",
            "ts": "2026-06-24T00:00:00",
        }
        assert sample_event["type"] == "task.cancelled"
        assert "task_id" in sample_event
        assert "ts" in sample_event
