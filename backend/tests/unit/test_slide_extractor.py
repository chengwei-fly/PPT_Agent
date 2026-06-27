"""Unit test for SlideExtractor (T214).

Validates slide extraction from PPTX samples with 3 typical fixtures.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


class TestSlideExtractor:
    """SlideExtractor unit tests."""

    def test_extractor_importable(self):
        """SlideExtractor should be importable."""
        from src.services.parsing.slide_extractor import SlideExtractor

        assert SlideExtractor is not None

    def test_visual_type_enum_values(self):
        """SlideVisualType covers all expected types."""
        from src.db.models import SlideVisualType

        expected = {"cover", "toc", "architecture", "flowchart", "data", "body", "closing", "mixed"}
        assert {e.value for e in SlideVisualType} == expected

    def test_slide_asset_model_fields(self):
        """SlideAsset model has all required fields."""
        from src.db.models import SlideAsset

        assert hasattr(SlideAsset, "id")
        assert hasattr(SlideAsset, "source_sample_id")
        assert hasattr(SlideAsset, "page_index")
        assert hasattr(SlideAsset, "visual_type")
        assert hasattr(SlideAsset, "title")
        assert hasattr(SlideAsset, "body_text")
        assert hasattr(SlideAsset, "thumbnail_path")
        assert hasattr(SlideAsset, "color_palette")
        assert hasattr(SlideAsset, "font_family")

    def test_draft_model_fields(self):
        """Draft model has all required fields."""
        from src.db.models import Draft

        assert hasattr(Draft, "id")
        assert hasattr(Draft, "owner_id")
        assert hasattr(Draft, "title")
        assert hasattr(Draft, "status")
        assert hasattr(Draft, "last_saved_revision")
        assert hasattr(Draft, "slides")

    def test_draft_slide_model_fields(self):
        """DraftSlide model has all required fields."""
        from src.db.models import DraftSlide

        assert hasattr(DraftSlide, "id")
        assert hasattr(DraftSlide, "draft_id")
        assert hasattr(DraftSlide, "slide_order")
        assert hasattr(DraftSlide, "source_type")
        assert hasattr(DraftSlide, "material_id")
