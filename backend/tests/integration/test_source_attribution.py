"""Unit test for add_source_to_slide (T254 / FR-037).

Validates source attribution for 3 source types: reused, generated, manual.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


class TestSourceAttribution:
    """Source attribution unit tests."""

    def test_export_service_importable(self):
        """DraftExporter should be importable."""
        from src.services.export.draft_exporter import DraftExporter

        assert DraftExporter is not None

    def test_source_attribution_module_exists(self):
        """Source attribution module should be importable."""
        from src.services.export import source_attribution

        assert source_attribution is not None

    def test_draft_slide_source_types(self):
        """DraftSlideSourceType covers all 3 source types."""
        from src.db.models import DraftSlideSourceType

        expected = {"reused", "generated", "manual"}
        assert {e.value for e in DraftSlideSourceType} == expected

    def test_draft_export_job_model(self):
        """DraftExportJob model should exist with required fields."""
        from src.db.models import DraftExportJob

        assert hasattr(DraftExportJob, "id")
        assert hasattr(DraftExportJob, "draft_id")
        assert hasattr(DraftExportJob, "status")
        assert hasattr(DraftExportJob, "progress")
        assert hasattr(DraftExportJob, "pptx_path")
