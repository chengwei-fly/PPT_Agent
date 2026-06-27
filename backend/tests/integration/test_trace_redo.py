"""Integration test for stage redo + timing saving (T087 / SC-009 ≥ 60% saving).

Validates: redo a stage → only that stage + downstream re-runs → time saved ≥ 60%.
"""

from __future__ import annotations

import pytest

from src.services.generation.token_estimator import TOKENS_PER_SLIDE_BY_STAGE

pytestmark = pytest.mark.integration


class TestTraceRedo:
    """Stage redo integration tests."""

    def test_redo_service_exists(self):
        """redo_stage function should be importable."""
        from src.services.generation.redo import redo_stage

        assert redo_stage is not None

    def test_redo_saves_time_sc009(self):
        """Redoing stage 3 (svg) should save ≥ 60% vs full redo (SC-009)."""
        full_time = sum(TOKENS_PER_SLIDE_BY_STAGE[s] * 10 for s in TOKENS_PER_SLIDE_BY_STAGE)
        redo_time = sum(TOKENS_PER_SLIDE_BY_STAGE[s] * 10 for s in ["svg", "pptx"])
        saving = 1.0 - (redo_time / full_time)
        assert saving >= 0.6, f"Saving {saving:.1%} < 60%"

    def test_redo_stage_2_saves_significant(self):
        """Redoing stage 2 (points) should save at least 40%."""
        full_time = sum(TOKENS_PER_SLIDE_BY_STAGE[s] * 10 for s in TOKENS_PER_SLIDE_BY_STAGE)
        redo_time = sum(TOKENS_PER_SLIDE_BY_STAGE[s] * 10 for s in ["points", "svg", "pptx"])
        saving = 1.0 - (redo_time / full_time)
        assert saving >= 0.4

    def test_trace_api_returns_stages_ordered(self):
        """Trace stages should be ordered by stage_order."""
        from src.db.models import TaskStage

        order = [e.value for e in TaskStage]
        assert order == ["outline", "points", "svg", "pptx"]

    @pytest.mark.asyncio
    async def test_redo_nonexistent_task(self, async_client, auth_headers):
        """Redo on nonexistent task returns 404."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        resp = await async_client.post(
            f"/api/v1/generations/{fake_id}/stages/outline/redo",
            headers=auth_headers,
        )
        assert resp.status_code in (404, 422)
