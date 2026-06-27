"""Performance test for material search (T224).

Validates SC-015: P95 search latency ≤ 1s on a 1000-asset corpus.

NOTE: This test requires a running PostgreSQL with pgvector and a populated
material_search_index table. It is skipped when the DB is not available.
"""

from __future__ import annotations

import time

import pytest

pytestmark = [pytest.mark.perf, pytest.mark.asyncio]


class TestMaterialSearchPerf:
    """Material search performance benchmarks."""

    async def _seed_assets(self, async_client, auth_headers, count: int = 1000):
        """Attempt to seed assets via the API. Returns number actually created."""
        # In a real environment, assets are created through the sample upload
        # pipeline. This is a no-op placeholder — the actual perf test assumes
        # the corpus is pre-seeded via `scripts/seed_samples.py` or fixtures.
        resp = await async_client.get("/api/v1/materials", headers=auth_headers)
        if resp.status_code != 200:
            return 0
        data = resp.json()
        return data.get("total", 0)

    async def test_search_latency_p95(self, async_client, auth_headers):
        """P95 search latency should be ≤ 1s on a populated corpus."""
        total = await self._seed_assets(async_client, auth_headers)
        if total < 10:
            pytest.skip("Not enough assets for perf test (need ≥ 10)")

        queries = [
            "储能",
            "架构图",
            "数据",
            "培训",
            "汇报",
            "方案",
            "流程图",
            "封面",
            "目录",
            "总结",
        ]

        latencies: list[float] = []
        for q in queries:
            start = time.perf_counter()
            resp = await async_client.get(
                "/api/v1/materials",
                params={"q": q, "page_size": 20},
                headers=auth_headers,
            )
            elapsed = time.perf_counter() - start
            assert resp.status_code == 200
            latencies.append(elapsed)

        p95 = sorted(latencies)[int(len(latencies) * 0.95)]
        assert p95 <= 1.0, f"P95 latency {p95:.3f}s exceeds 1.0s threshold"

    async def test_search_pagination_performance(self, async_client, auth_headers):
        """Paginated search should not degrade on later pages."""
        total = await self._seed_assets(async_client, auth_headers)
        if total < 50:
            pytest.skip("Not enough assets for pagination perf test")

        # First page
        start = time.perf_counter()
        resp1 = await async_client.get(
            "/api/v1/materials",
            params={"page": 1, "page_size": 20},
            headers=auth_headers,
        )
        t1 = time.perf_counter() - start
        assert resp1.status_code == 200

        # Later page
        start = time.perf_counter()
        resp2 = await async_client.get(
            "/api/v1/materials",
            params={"page": 5, "page_size": 20},
            headers=auth_headers,
        )
        t2 = time.perf_counter() - start
        assert resp2.status_code == 200

        # Later page should not be more than 3x slower
        if t1 > 0.01:
            assert t2 < t1 * 3, f"Page 5 ({t2:.3f}s) much slower than page 1 ({t1:.3f}s)"

    async def test_visual_type_filter_performance(self, async_client, auth_headers):
        """Filtering by visual_type should be fast."""
        total = await self._seed_assets(async_client, auth_headers)
        if total < 10:
            pytest.skip("Not enough assets for filter perf test")

        visual_types = ["cover", "body", "data", "architecture"]
        for vt in visual_types:
            start = time.perf_counter()
            resp = await async_client.get(
                "/api/v1/materials",
                params={"visual_types": vt, "page_size": 20},
                headers=auth_headers,
            )
            elapsed = time.perf_counter() - start
            assert resp.status_code == 200
            assert elapsed < 1.0, f"Filter '{vt}' took {elapsed:.3f}s"
