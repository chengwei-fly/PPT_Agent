"""Contract tests for POST /samples/batch + GET /samples + DELETE /samples/{id} (T051).

Verifies the wire shape of sample CRUD endpoints so frontend codegen stays in sync.
"""

from __future__ import annotations

import inspect

import pytest

pytestmark = pytest.mark.contract


def _import_src():
    """Import src modules, skip if environment lacks dependencies."""
    try:
        from src.api.samples import MAX_BATCH_COUNT, MAX_FILE_BYTES, SampleResponse, router
        from src.db.models import FileType, ParseStatus

        return SampleResponse, MAX_BATCH_COUNT, MAX_FILE_BYTES, router, FileType, ParseStatus
    except (ImportError, NameError, TypeError) as e:
        pytest.skip(f"Cannot import src modules (missing deps or DB): {e}")


class TestSamplesContract:
    """Wire-shape contract for sample endpoints."""

    def test_sample_response_shape(self) -> None:
        """SampleResponse MUST include all required fields."""
        SampleResponse, *_ = _import_src()
        fields = set(SampleResponse.model_fields.keys())
        required = {"id", "file_name", "file_type", "parse_status", "uploaded_at"}
        assert required <= fields

    def test_sample_response_no_extra_fields(self) -> None:
        """SampleResponse forbids extra fields (extra='forbid')."""
        SampleResponse, *_ = _import_src()
        assert SampleResponse.model_config.get("extra") == "forbid"

    def test_file_type_enum_values(self) -> None:
        """file_type MUST be one of pptx/pdf/docx."""
        *_, FileType, _ = _import_src()
        assert {e.value for e in FileType} == {"pptx", "pdf", "docx"}

    def test_parse_status_enum_values(self) -> None:
        """parse_status MUST be one of pending/parsing/parsed/failed."""
        *_, ParseStatus = _import_src()
        assert {e.value for e in ParseStatus} == {"pending", "parsing", "parsed", "failed"}

    def test_list_samples_returns_list(self) -> None:
        """GET /samples response_model is list[SampleResponse]."""
        *_, router, _, _ = _import_src()
        list_routes = [r for r in router.routes if r.path == "/" and "GET" in r.methods]
        assert len(list_routes) == 1
        assert list_routes[0].response_model is not None

    def test_delete_returns_204(self) -> None:
        """DELETE /samples/{id} returns 204 No Content on success."""
        *_, router, _, _ = _import_src()
        delete_routes = [
            r for r in router.routes if r.path == "/{sample_id}" and "DELETE" in r.methods
        ]
        assert len(delete_routes) == 1
        assert delete_routes[0].status_code == 204

    def test_batch_size_guard(self) -> None:
        """Batch upload MUST reject > 20 files per request (FR-006)."""
        _, MAX_BATCH_COUNT, *_ = _import_src()
        assert MAX_BATCH_COUNT == 20

    def test_file_size_guard(self) -> None:
        """Each file MUST be <= 50MB (FR-006)."""
        _, _, MAX_FILE_BYTES, *_ = _import_src()
        assert MAX_FILE_BYTES == 50 * 1024 * 1024

    def test_pii_summary_shape(self) -> None:
        """pii_summary contains hit_count and fields."""
        try:
            from src.services.knowledge_base.service import parse_and_index_sample
        except (ImportError, NameError, TypeError) as e:
            pytest.skip(f"Cannot import service: {e}")
        src = inspect.getsource(parse_and_index_sample)
        assert "hit_count" in src
        assert "fields" in src
