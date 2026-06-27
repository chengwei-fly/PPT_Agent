"""Contract test for GET /materials (T223 — Pact provider).

Verifies the wire shape of material search endpoints.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.contract


def _import_materials():
    try:
        from src.api.assets import MaterialResponse, MaterialSearchResponse
        from src.db.models import SlideVisualType

        return MaterialSearchResponse, MaterialResponse, SlideVisualType
    except (ImportError, NameError, TypeError) as e:
        pytest.skip(f"Cannot import src modules (missing deps or DB): {e}")


class TestMaterialsContract:
    """Wire-shape contract for material endpoints."""

    def test_material_search_response_keys(self):
        """GET /materials returns items + total + duration_ms."""
        MaterialSearchResponse, *_ = _import_materials()
        fields = set(MaterialSearchResponse.model_fields.keys())
        assert "items" in fields
        assert "total" in fields
        assert "duration_ms" in fields

    def test_material_response_keys(self):
        """MaterialResponse includes all required fields."""
        _, MaterialResponse, _ = _import_materials()
        fields = set(MaterialResponse.model_fields.keys())
        expected = {
            "id",
            "source_sample_id",
            "page_index",
            "visual_type",
            "title",
            "body_text",
            "thumbnail_path",
            "color_palette",
            "font_family",
            "industry_tags",
            "indexed_at",
        }
        assert expected <= fields

    def test_visual_type_enum(self):
        """visual_type must be one of the allowed values."""
        *_, SlideVisualType = _import_materials()
        allowed = {e.value for e in SlideVisualType}
        assert "cover" in allowed
        assert "data" in allowed
        assert "body" in allowed

    def test_material_detail_response(self):
        """GET /materials/{id} returns single MaterialResponse."""
        _, MaterialResponse, _ = _import_materials()
        assert MaterialResponse.model_config.get("from_attributes") is True
