"""Contract tests for POST /data/export + POST /data/delete-all (T094).

Verifies the wire shape of data lifecycle endpoints.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.contract


def _import_src():
    """Import src modules, skip if environment lacks dependencies."""
    try:
        from src.api.data_lifecycle import DeleteAllRequest, ExportRequest, ExportResponse
        from src.db.models import SecurityAction, SecurityEventType

        return ExportResponse, ExportRequest, DeleteAllRequest, SecurityEventType, SecurityAction
    except (ImportError, NameError, TypeError) as e:
        pytest.skip(f"Cannot import src modules (missing deps or DB): {e}")


class TestDataLifecycleContract:
    """Wire-shape contract for data lifecycle endpoints."""

    def test_export_response_shape(self) -> None:
        """POST /data/export returns ExportResponse with required fields."""
        ExportResponse, *_ = _import_src()
        fields = set(ExportResponse.model_fields.keys())
        assert {"job_id", "status", "message"} <= fields

    def test_export_request_defaults(self) -> None:
        """ExportRequest.confirm defaults to False."""
        _, ExportRequest, *_ = _import_src()
        req = ExportRequest()
        assert req.confirm is False

    def test_delete_all_requires_confirmation_phrase(self) -> None:
        """POST /data/delete-all requires confirmation_phrase field."""
        *_, DeleteAllRequest, _, _ = _import_src()
        fields = set(DeleteAllRequest.model_fields.keys())
        assert "confirmation_phrase" in fields

    def test_security_event_types(self) -> None:
        """SecurityEventType covers all expected event types."""
        *_, SecurityEventType, _ = _import_src()
        expected = {
            "pii_hit",
            "pii_blocked",
            "pii_replaced",
            "pii_acknowledged",
            "unauth_access",
            "bulk_export",
            "bulk_delete",
        }
        assert {e.value for e in SecurityEventType} == expected

    def test_security_actions(self) -> None:
        """SecurityAction covers replace/block/allow."""
        *_, SecurityAction = _import_src()
        assert {e.value for e in SecurityAction} == {"replace", "block", "allow"}
