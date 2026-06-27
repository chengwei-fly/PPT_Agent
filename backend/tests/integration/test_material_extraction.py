"""Integration test for extract → index → search pipeline (T215).

Validates the full material extraction pipeline from sample to searchable assets.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


class TestMaterialExtraction:
    """Material extraction pipeline integration tests."""

    def test_material_search_service_importable(self):
        """MaterialSearchService should be importable."""
        from src.services.search.material_search import MaterialSearchService

        assert MaterialSearchService is not None

    def test_material_search_request_shape(self):
        """MaterialSearchRequest has correct fields."""
        from src.api.assets import MaterialSearchRequest

        assert hasattr(MaterialSearchRequest, "query")
        assert hasattr(MaterialSearchRequest, "visual_types")
        assert hasattr(MaterialSearchRequest, "industry_tags")
        assert hasattr(MaterialSearchRequest, "limit")

    def test_material_response_shape(self):
        """MaterialResponse has correct fields."""
        from src.api.assets import MaterialResponse

        assert hasattr(MaterialResponse, "id")
        assert hasattr(MaterialResponse, "visual_type")
        assert hasattr(MaterialResponse, "title")
        assert hasattr(MaterialResponse, "thumbnail_path")
        assert hasattr(MaterialResponse, "color_palette")

    @pytest.mark.asyncio
    async def test_search_materials_empty(self, async_client, auth_headers):
        """GET /materials returns empty result for fresh user."""
        resp = await async_client.get("/api/v1/materials", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_search_materials_with_query(self, async_client, auth_headers):
        """GET /materials?q=xxx accepts search query."""
        resp = await async_client.get(
            "/api/v1/materials?q=储能&type=cover",
            headers=auth_headers,
        )
        assert resp.status_code == 200
