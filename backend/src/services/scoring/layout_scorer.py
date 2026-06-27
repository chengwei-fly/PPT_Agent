"""LayoutScorer (FR-028 / T111) — score layout structure variety + consistency."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.observability import get_logger
from src.db.models import TraceStage

logger = get_logger("scoring.layout")


class LayoutScorer:
    """Score the layout structure variety + consistency of a generated PPT."""

    name = "layout"

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def score(self, task_id: uuid.UUID) -> float:
        stages = (
            (await self.session.execute(select(TraceStage).where(TraceStage.task_id == task_id)))
            .scalars()
            .all()
        )
        layouts = [s.output_summary for s in stages if s.stage_name == "svg" and s.output_summary]
        if not layouts:
            return 0.0
        # Penalize all-same layout, reward variety
        unique = set(layouts)
        variety = len(unique) / max(len(layouts), 1)
        # Coverage: each unique layout should be >= 5% of total
        coverage = min(
            1.0, sum(1 for l in layouts if layouts.count(l) >= len(layouts) * 0.05) / len(layouts)
        )
        return round((variety + coverage) / 2, 3)
