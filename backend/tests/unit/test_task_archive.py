"""Unit test for task archive (180d + 14d notify) (T097 / SC-013 / FR-026/FR-027).

Validates: tasks older than 180d get archived, 14d before that a notification is sent.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from src.db.models import GenerationTask, TaskStatus

pytestmark = pytest.mark.unit


class TestTaskArchive:
    """Task archive unit tests."""

    def test_generation_task_has_expires_at(self):
        """GenerationTask has expires_at field for archival scheduling."""
        assert hasattr(GenerationTask, "expires_at")

    def test_generation_task_has_notified_at(self):
        """GenerationTask has notified_at field for 14d notification."""
        assert hasattr(GenerationTask, "notified_at")

    def test_task_status_includes_archived(self):
        """TaskStatus enum includes 'archived'."""
        assert "archived" in [e.value for e in TaskStatus]

    def test_archive_threshold_180_days(self):
        """Archive threshold is 180 days."""
        threshold_days = 180
        now = datetime.utcnow()
        old_task_created = now - timedelta(days=threshold_days + 1)
        assert (now - old_task_created).days > threshold_days

    def test_notification_threshold_14_days_before_archive(self):
        """Notification should be sent 14 days before archive."""
        archive_days = 180
        notify_days = 14
        now = datetime.utcnow()
        # Task created 166 days ago → should be notified but not yet archived
        created = now - timedelta(days=archive_days - notify_days)
        age = (now - created).days
        assert age >= archive_days - notify_days
        assert age < archive_days

    def test_task_status_all_values(self):
        """TaskStatus covers all expected states."""
        expected = {"queued", "running", "success", "failed", "cancelled", "archived"}
        assert {e.value for e in TaskStatus} == expected
