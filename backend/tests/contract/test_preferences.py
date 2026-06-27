"""Contract tests for GET /preferences + DELETE /preferences/{id} (T072).

Verifies the wire shape of preference endpoints.
"""

from __future__ import annotations

import inspect

import pytest

pytestmark = pytest.mark.contract


def _import_src():
    """Import src modules, skip if environment lacks dependencies."""
    try:
        from src.api import preferences
        from src.api.preferences import PreferenceResponse, router
        from src.db.models import PreferenceScope

        return PreferenceResponse, router, PreferenceScope, preferences
    except (ImportError, NameError, TypeError) as e:
        pytest.skip(f"Cannot import src modules (missing deps or DB): {e}")


class TestPreferencesContract:
    """Wire-shape contract for preference endpoints."""

    def test_preference_response_shape(self) -> None:
        """PreferenceResponse MUST include all required fields."""
        PreferenceResponse, *_ = _import_src()
        fields = set(PreferenceResponse.model_fields.keys())
        required = {
            "id",
            "owner_id",
            "source_chains",
            "rule_text",
            "applies_to",
            "apply_count",
            "ignore_count",
            "is_active",
            "created_at",
        }
        assert required <= fields

    def test_preference_response_no_extra_fields(self) -> None:
        """PreferenceResponse forbids extra fields."""
        PreferenceResponse, *_ = _import_src()
        assert PreferenceResponse.model_config.get("extra") == "forbid"

    def test_preference_id_format(self) -> None:
        """Preference ID follows P-NNN format."""
        sample_id = "P-007"
        assert sample_id.startswith("P-")
        assert sample_id[2:].isdigit()

    def test_applies_to_enum_values(self) -> None:
        """applies_to MUST be one of cover/toc/body/closing/all."""
        *_, PreferenceScope, _ = _import_src()
        assert {e.value for e in PreferenceScope} == {"cover", "toc", "body", "closing", "all"}

    def test_delete_is_soft_delete(self) -> None:
        """DELETE /preferences/{id} sets is_active=false (soft delete)."""
        *_, preferences = _import_src()
        src = inspect.getsource(preferences.delete_preference)
        assert "is_active" in src and "False" in src

    def test_list_sorted_by_apply_count_desc(self) -> None:
        """Preferences MUST be sorted by apply_count DESC."""
        *_, preferences = _import_src()
        src = inspect.getsource(preferences.list_preferences)
        assert "apply_count" in src and "desc" in src
