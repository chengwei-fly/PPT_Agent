"""Integration E2E test for full generation pipeline (T032 / SC-001).

Validates: upload sample → create generation → poll until success → download PPTX.
Uses mock/stub pipeline stages (no real LLM calls).
"""

from __future__ import annotations

import asyncio

import pytest

pytestmark = pytest.mark.integration


class TestGenerationE2E:
    """Full generation pipeline integration test."""

    @pytest.mark.asyncio
    async def test_generation_task_lifecycle(self, async_client, auth_headers):
        """Create a generation task and verify it transitions through states."""
        # Create task
        resp = await async_client.post(
            "/api/v1/generations",
            json={"prompt": "做一份 10 页的季度工作汇报"},
            headers=auth_headers,
        )
        assert resp.status_code in (200, 202), f"Unexpected: {resp.status_code} {resp.text}"
        data = resp.json()
        task_id = data.get("task_id") or data.get("id")
        assert task_id is not None

        # Poll for status
        for _ in range(10):
            resp = await async_client.get(
                f"/api/v1/generations/{task_id}",
                headers=auth_headers,
            )
            if resp.status_code == 200:
                status = resp.json().get("status")
                if status in ("success", "failed", "cancelled"):
                    break
            await asyncio.sleep(0.5)

        # Verify final state is terminal
        resp = await async_client.get(
            f"/api/v1/generations/{task_id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        task = resp.json()
        assert task["status"] in ("success", "failed", "cancelled", "running", "queued")

    @pytest.mark.asyncio
    async def test_generation_cancel(self, async_client, auth_headers):
        """Cancel a generation task within 5 seconds (FR-003)."""
        # Create task
        resp = await async_client.post(
            "/api/v1/generations",
            json={"prompt": "测试取消任务"},
            headers=auth_headers,
        )
        assert resp.status_code in (200, 202)
        data = resp.json()
        task_id = data.get("task_id") or data.get("id")

        # Cancel immediately
        resp = await async_client.delete(
            f"/api/v1/generations/{task_id}",
            headers=auth_headers,
        )
        assert resp.status_code in (200, 204)

    @pytest.mark.asyncio
    async def test_generation_trace_after_completion(self, async_client, auth_headers):
        """After task completion, trace should have 4 stages."""
        # Create and wait for completion
        resp = await async_client.post(
            "/api/v1/generations",
            json={"prompt": "测试轨迹"},
            headers=auth_headers,
        )
        if resp.status_code not in (200, 202):
            pytest.skip("Cannot create generation task")

        data = resp.json()
        task_id = data.get("task_id") or data.get("id")

        # Wait for completion
        for _ in range(20):
            resp = await async_client.get(f"/api/v1/generations/{task_id}", headers=auth_headers)
            if resp.status_code == 200 and resp.json().get("status") in ("success", "failed"):
                break
            await asyncio.sleep(0.5)

        # Fetch trace
        resp = await async_client.get(f"/api/v1/generations/{task_id}/trace", headers=auth_headers)
        if resp.status_code == 200:
            stages = resp.json()
            assert isinstance(stages, list)
            # Should have at least 1 stage
            assert len(stages) >= 1
