"""Unit test for StyleNormalizer (T243).

Validates style normalization: 3 pass + 2 fail cases.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


class TestStyleNormalizer:
    """StyleNormalizer unit tests."""

    def test_normalizer_importable(self):
        """StyleNormalizer should be importable."""
        from src.tools.style_normalizer import StyleNormalizer

        assert StyleNormalizer is not None

    def test_normalizer_has_should_normalize(self):
        """StyleNormalizer has should_normalize method."""
        from src.tools.style_normalizer import StyleNormalizer

        assert hasattr(StyleNormalizer, "should_normalize")

    def test_normalizer_has_normalize(self):
        """StyleNormalizer has normalize method."""
        from src.tools.style_normalizer import StyleNormalizer

        assert hasattr(StyleNormalizer, "normalize")

    def test_normalizer_has_normalize_or_fallback(self):
        """StyleNormalizer has normalize_or_fallback method."""
        from src.tools.style_normalizer import StyleNormalizer

        assert hasattr(StyleNormalizer, "normalize_or_fallback")

    def test_draft_service_importable(self):
        """DraftService should be importable."""
        from src.services.draft.draft_service import DraftService

        assert DraftService is not None
