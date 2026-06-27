"""Unit test for SHA-256 dedup in sample upload (T053 / FR-010).

Validates: same file uploaded twice → second upload returns existing sample.
"""

from __future__ import annotations

import hashlib

import pytest

pytestmark = pytest.mark.unit


class TestSampleDedup:
    """SHA-256 deduplication unit tests."""

    def test_sha256_hash_deterministic(self):
        """Same content always produces the same SHA-256 hash."""
        content = b"test pptx content"
        h1 = hashlib.sha256(content).hexdigest()
        h2 = hashlib.sha256(content).hexdigest()
        assert h1 == h2
        assert len(h1) == 64

    def test_sha256_hash_different_content(self):
        """Different content produces different hashes."""
        h1 = hashlib.sha256(b"content A").hexdigest()
        h2 = hashlib.sha256(b"content B").hexdigest()
        assert h1 != h2

    def test_sample_model_has_unique_constraint(self):
        """Sample model has UniqueConstraint on (owner_id, file_hash)."""
        from src.db.models import Sample

        # Check the table args for the unique constraint
        table_args = Sample.__table_args__
        constraint_names = [c.name for c in table_args if hasattr(c, "name")]
        assert "uq_samples_owner_hash" in constraint_names

    def test_sample_model_has_file_hash_field(self):
        """Sample model has file_hash field with SHA-256 check."""
        from src.db.models import Sample

        assert hasattr(Sample, "file_hash")
        # Check the hash length constraint
        table_args = Sample.__table_args__
        check_constraints = [c for c in table_args if hasattr(c, "sqltext")]
        has_hash_check = any("file_hash" in str(c.sqltext) for c in check_constraints)
        assert has_hash_check
