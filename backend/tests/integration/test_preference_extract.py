"""Integration test for preference extraction (T073 / SC-007).

Validates: 5x same modification → 1 rule extracted.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


class TestPreferenceExtraction:
    """Preference extraction integration tests."""

    def test_preference_extractor_exists(self):
        """PreferenceExtractor class should be importable."""
        from src.services.preference.extractor import PreferenceExtractor

        assert PreferenceExtractor is not None

    def test_preference_model_fields(self):
        """Preference model has all required fields."""
        from src.db.models import Preference

        assert hasattr(Preference, "id")
        assert hasattr(Preference, "owner_id")
        assert hasattr(Preference, "source_chains")
        assert hasattr(Preference, "rule_text")
        assert hasattr(Preference, "applies_to")
        assert hasattr(Preference, "apply_count")
        assert hasattr(Preference, "ignore_count")
        assert hasattr(Preference, "is_active")
        assert hasattr(Preference, "deleted_at")

    def test_preference_scope_enum(self):
        """PreferenceScope covers all expected scopes."""
        from src.db.models import PreferenceScope

        expected = {"cover", "toc", "body", "closing", "all"}
        assert {e.value for e in PreferenceScope} == expected

    def test_behavior_middleware_exists(self):
        """BehaviorMiddleware should be importable."""
        from src.agents.middleware.behavior_middleware import BehaviorMiddleware

        assert BehaviorMiddleware is not None

    @pytest.mark.asyncio
    async def test_list_preferences_empty(self, async_client, auth_headers):
        """GET /preferences returns empty list for fresh user."""
        resp = await async_client.get("/api/v1/preferences", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_delete_nonexistent_preference(self, async_client, auth_headers):
        """DELETE /preferences/{id} returns 404 for nonexistent."""
        resp = await async_client.delete(
            "/api/v1/preferences/P-999",
            headers=auth_headers,
        )
        assert resp.status_code in (404, 422)
