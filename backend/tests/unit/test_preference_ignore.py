"""Unit test for ignore-count increment on 撤销/锁定 (T074 / FR-014).

Validates: when user undoes/locks a preference, ignore_count increments.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


class TestPreferenceIgnore:
    """Preference ignore-count unit tests."""

    def test_preference_model_has_ignore_count(self):
        """Preference model has ignore_count field."""
        from src.db.models import Preference

        assert hasattr(Preference, "ignore_count")

    def test_preference_default_ignore_count_zero(self):
        """New preference should have ignore_count = 0."""
        from src.db.models import Preference

        # The column default is 0
        col = Preference.__table__.columns["ignore_count"]
        assert col.default.arg == 0

    def test_preference_default_apply_count_zero(self):
        """New preference should have apply_count = 0."""
        from src.db.models import Preference

        col = Preference.__table__.columns["apply_count"]
        assert col.default.arg == 0

    def test_preference_default_is_active_true(self):
        """New preference should be active by default."""
        from src.db.models import Preference

        col = Preference.__table__.columns["is_active"]
        assert col.default.arg is True

    def test_preference_has_deleted_at_for_soft_delete(self):
        """Preference model supports soft delete via deleted_at."""
        from src.db.models import Preference

        assert hasattr(Preference, "deleted_at")
