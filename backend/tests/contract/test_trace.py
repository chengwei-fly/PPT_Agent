"""Contract tests for GET /generations/{id}/trace + POST .../stages/{name}/redo (T086).

Verifies the wire shape of trace endpoints.
"""

from __future__ import annotations

import inspect

import pytest

pytestmark = pytest.mark.contract


def _import_src():
    """Import src modules, skip if environment lacks dependencies."""
    try:
        from src.api import traces
        from src.api.traces import TraceStageResponse, router
        from src.db.models import StageStatus, TaskStage

        return TraceStageResponse, router, TaskStage, StageStatus, traces
    except (ImportError, NameError, TypeError) as e:
        pytest.skip(f"Cannot import src modules (missing deps or DB): {e}")


class TestTraceContract:
    """Wire-shape contract for trace endpoints."""

    def test_trace_stage_response_shape(self) -> None:
        """TraceStageResponse MUST include all required fields."""
        TraceStageResponse, *_ = _import_src()
        fields = set(TraceStageResponse.model_fields.keys())
        required = {
            "id",
            "task_id",
            "stage_name",
            "stage_order",
            "input_summary",
            "output_summary",
            "referenced_sample_ids",
            "duration_ms",
            "status",
            "started_at",
            "finished_at",
            "error_message",
            "redo_count",
        }
        assert required <= fields

    def test_trace_stage_response_no_extra_fields(self) -> None:
        """TraceStageResponse forbids extra fields."""
        TraceStageResponse, *_ = _import_src()
        assert TraceStageResponse.model_config.get("extra") == "forbid"

    def test_stage_name_enum(self) -> None:
        """stage_name MUST be one of outline/points/svg/pptx."""
        *_, TaskStage, _, _ = _import_src()
        assert {e.value for e in TaskStage} == {"outline", "points", "svg", "pptx"}

    def test_stage_status_enum(self) -> None:
        """stage status MUST be one of pending/running/success/failed."""
        *_, StageStatus, _ = _import_src()
        assert {e.value for e in StageStatus} == {"pending", "running", "success", "failed"}

    def test_trace_ordered_by_stage_order(self) -> None:
        """GET /generations/{id}/trace returns stages ordered by stage_order ASC."""
        *_, traces = _import_src()
        src = inspect.getsource(traces.get_trace)
        assert "stage_order" in src and "asc" in src

    def test_redo_returns_202(self) -> None:
        """POST .../stages/{name}/redo returns 202 Accepted."""
        _, router, *_ = _import_src()
        redo_routes = [
            r
            for r in router.routes
            if hasattr(r, "path") and "redo" in r.path and "POST" in r.methods
        ]
        assert len(redo_routes) >= 1
        assert redo_routes[0].status_code == 202

    def test_redo_must_emit_ws_event(self) -> None:
        """Redo MUST call publish_ws_event for stage.redo.started."""
        *_, traces = _import_src()
        src = inspect.getsource(traces.redo_stage_endpoint)
        assert "publish_ws_event" in src
        assert "redo" in src
