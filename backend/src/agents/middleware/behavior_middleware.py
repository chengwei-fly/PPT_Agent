"""Behavior middleware — auto-apply preferences + ignore-count tracking (FR-012/FR-014)."""

from __future__ import annotations

from src.core.observability import get_logger
from src.db.models import Preference

logger = get_logger("behavior_middleware")


class BehaviorMiddleware:
    """Reads active preferences, applies matching ones, tracks ignore count."""

    def __init__(self) -> None:
        self._lock_map: dict[str, str] = {}  # task_id → locked original text

    def lock_original_text(self, task_id: str, original_text: str) -> None:
        """FR-017: User can lock original text; preference MUST NOT modify it."""
        self._lock_map[task_id] = original_text

    def is_locked(self, task_id: str) -> bool:
        return task_id in self._lock_map

    def select_applicable(self, preferences: list[Preference], stage: str) -> list[Preference]:
        """Select active preferences that match the current stage."""
        return [
            p
            for p in preferences
            if p.is_active
            and p.deleted_at is None
            and (p.applies_to.value == stage or p.applies_to.value == "all")
        ]

    def record_applied(self, preference: Preference) -> None:
        preference.apply_count += 1

    def record_ignored(self, preference: Preference) -> None:
        """FR-014: When user undoes/locks, increment ignore_count."""
        preference.ignore_count += 1
