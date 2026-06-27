"""Unit tests for ORM model structure.

These are pure structural tests (no DB needed) — they verify that the
model classes are importable, that __tablename__ matches expectations,
and that the registered enums are consistent.
"""

from __future__ import annotations


def test_models_importable():
    from src.db.models import (
        ApiKey,
        Draft,
        DraftExportJob,
        DraftSlide,
        Embedding,
        GenerationTask,
        IdempotencyKey,
        MaterialSearchIndex,
        ParseResult,
        Preference,
        Sample,
        SecurityEvent,
        SlideAsset,
        TraceStage,
        User,
    )

    # Just verify they all imported
    assert User.__tablename__ == "users"
    assert ApiKey.__tablename__ == "api_keys"
    assert IdempotencyKey.__tablename__ == "idempotency_keys"
    assert Sample.__tablename__ == "samples"
    assert ParseResult.__tablename__ == "parse_results"
    assert Embedding.__tablename__ == "embeddings"
    assert Preference.__tablename__ == "preferences"
    assert GenerationTask.__tablename__ == "generation_tasks"
    assert TraceStage.__tablename__ == "trace_stages"
    assert SecurityEvent.__tablename__ == "security_events"
    assert SlideAsset.__tablename__ == "slide_assets"
    assert Draft.__tablename__ == "drafts"
    assert DraftSlide.__tablename__ == "draft_slides"
    assert MaterialSearchIndex.__tablename__ == "material_search_index"
    assert DraftExportJob.__tablename__ == "draft_export_jobs"


def test_enums_have_expected_values():
    from src.db.models import (
        FileType,
        ParseStatus,
        PreferenceScope,
        SecurityAction,
        SecurityEventType,
        StageStatus,
        TaskStage,
        TaskStatus,
        UserTier,
    )

    assert {e.value for e in UserTier} == {"personal", "team", "enterprise"}
    assert {e.value for e in FileType} == {"pptx", "pdf", "docx"}
    assert {e.value for e in ParseStatus} == {"pending", "parsing", "parsed", "failed"}
    assert {e.value for e in TaskStatus} == {
        "queued",
        "running",
        "success",
        "failed",
        "cancelled",
        "archived",
    }
    assert {e.value for e in TaskStage} == {"outline", "points", "svg", "pptx"}
    assert {e.value for e in StageStatus} == {"pending", "running", "success", "failed"}
    assert {e.value for e in PreferenceScope} == {"cover", "toc", "body", "closing", "all"}
    assert {e.value for e in SecurityEventType} == {
        "pii_hit",
        "pii_blocked",
        "pii_replaced",
        "pii_acknowledged",
        "unauth_access",
        "bulk_export",
        "bulk_delete",
    }
    assert {e.value for e in SecurityAction} == {"replace", "block", "allow"}


def test_models_registered_on_base_metadata():
    from src.db.models import (  # noqa: F401
        ApiKey,
        Draft,
        DraftExportJob,
        DraftSlide,
        Embedding,
        GenerationTask,
        IdempotencyKey,
        MaterialSearchIndex,
        ParseResult,
        Preference,
        Sample,
        SecurityEvent,
        SlideAsset,
        TraceStage,
        User,
    )
    from src.db.models.base import Base

    table_names = set(Base.metadata.tables.keys())
    expected = {
        "users",
        "api_keys",
        "idempotency_keys",
        "samples",
        "parse_results",
        "embeddings",
        "preferences",
        "generation_tasks",
        "trace_stages",
        "security_events",
        "slide_assets",
        "drafts",
        "draft_slides",
        "material_search_index",
        "draft_export_jobs",
    }
    assert expected <= table_names


def test_relationships_resolve():
    """Verify relationships are wired without instantiating (i.e. no
    import-time circular dependency issues)."""
    from src.db.models import Draft, GenerationTask, Sample, User

    # Class-level relationship access
    assert hasattr(User, "samples")
    assert hasattr(User, "generation_tasks")
    assert hasattr(User, "preferences")
    assert hasattr(User, "drafts")
    assert hasattr(Sample, "parse_result")
    assert hasattr(GenerationTask, "trace_stages")
    assert hasattr(Draft, "slides")
    assert hasattr(Draft, "export_jobs")
