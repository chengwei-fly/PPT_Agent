"""Contract test for draft CRUD + lock + revision mismatch (T237).

Verifies the wire shape of draft endpoints.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.contract


def _import_drafts():
    try:
        from src.api.drafts import (
            CreateDraftRequest,
            DraftResponse,
            DraftSlideResponse,
            InsertSlideRequest,
            UpdateDraftRequest,
        )
        from src.db.models import DraftSlideSourceType

        return (
            DraftResponse,
            DraftSlideResponse,
            CreateDraftRequest,
            UpdateDraftRequest,
            InsertSlideRequest,
            DraftSlideSourceType,
        )
    except (ImportError, NameError, TypeError) as e:
        pytest.skip(f"Cannot import src modules (missing deps or DB): {e}")


class TestDraftsContract:
    """Wire-shape contract for draft endpoints."""

    def test_draft_response_keys(self):
        """DraftResponse includes all required fields."""
        DraftResponse, *_ = _import_drafts()
        fields = set(DraftResponse.model_fields.keys())
        expected = {
            "id",
            "owner_id",
            "title",
            "status",
            "last_saved_revision",
            "editor_user_id",
            "lock_acquired_at",
            "lock_expires_at",
            "created_at",
            "updated_at",
        }
        assert expected <= fields

    def test_draft_slide_response_keys(self):
        """DraftSlideResponse includes all required fields."""
        _, DraftSlideResponse, *_ = _import_drafts()
        fields = set(DraftSlideResponse.model_fields.keys())
        expected = {
            "id",
            "draft_id",
            "slide_order",
            "source_type",
            "material_id",
            "generated_stage_id",
            "title",
            "body_text",
            "notes",
        }
        assert expected <= fields

    def test_create_draft_request_requires_title(self):
        """CreateDraftRequest requires title (min_length=1)."""
        *_, CreateDraftRequest, _, _, _ = _import_drafts()
        field = CreateDraftRequest.model_fields["title"]
        assert field.is_required()

    def test_update_draft_request_requires_revision(self):
        """UpdateDraftRequest requires last_saved_revision for optimistic locking."""
        *_, UpdateDraftRequest, _, _ = _import_drafts()
        field = UpdateDraftRequest.model_fields["last_saved_revision"]
        assert field.is_required()

    def test_insert_slide_request_shape(self):
        """InsertSlideRequest accepts material_id or generated_stage_id."""
        *_, InsertSlideRequest, _ = _import_drafts()
        fields = set(InsertSlideRequest.model_fields.keys())
        assert "material_id" in fields
        assert "generated_stage_id" in fields
        assert "insert_at" in fields

    def test_draft_source_type_enum(self):
        """DraftSlideSourceType covers reused/generated/manual."""
        *_, DraftSlideSourceType = _import_drafts()
        expected = {"reused", "generated", "manual"}
        assert {e.value for e in DraftSlideSourceType} == expected
