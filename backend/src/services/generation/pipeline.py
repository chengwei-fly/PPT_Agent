"""DEPRECATED — fixed 4-stage generation pipeline.

⚠ This module is the LEGACY fixed-pipeline orchestrator and is
NO LONGER the production code path. It is kept here for
back-compat with old test fixtures only.

The new ReAct-driven orchestrator lives in
``src.agents.orchestrator.OrchestratorAgent`` and is invoked by
``src.scheduler.worker.process_generation_task``.

See the commit history of ``src/agents/orchestrator.py`` and
``src/scheduler/worker.py`` for the rationale and migration notes.
"""

from __future__ import annotations

import warnings
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.orchestrator import OrchestratorAgent
from src.core.observability import get_logger
from src.db.models import GenerationTask

logger = get_logger("pipeline.deprecated")

# Emit a deprecation warning exactly once at import time
warnings.warn(
    "src.services.generation.pipeline is deprecated; use "
    "src.agents.orchestrator.OrchestratorAgent instead.",
    DeprecationWarning,
    stacklevel=2,
)

STAGE_ORDER = ["outline", "points", "svg", "pptx"]


class GenerationPipeline:  # pragma: no cover - legacy shim
    """Deprecated. Use :class:`src.agents.orchestrator.OrchestratorAgent`."""

    def __init__(self, session: AsyncSession, task_id: str) -> None:
        self.session = session
        self._task_id_str = task_id
        self.task: GenerationTask | None = None
        self._deprecation_warned = False

    def _warn(self) -> None:
        if not self._deprecation_warned:
            warnings.warn(
                "GenerationPipeline is deprecated. The ReAct orchestrator "
                "(OrchestratorAgent) will be used instead.",
                DeprecationWarning,
                stacklevel=3,
            )
            self._deprecation_warned = True

    async def run(self) -> None:
        """Forward to the new OrchestratorAgent."""
        import uuid as _uuid

        from sqlalchemy import select

        self._warn()
        task = (
            await self.session.execute(
                select(GenerationTask).where(
                    GenerationTask.id == _uuid.UUID(self._task_id_str)
                )
            )
        ).scalar_one_or_none()
        if not task:
            logger.error("task_not_found", task_id=self._task_id_str)
            return
        orchestrator = OrchestratorAgent(self.session, task)
        await orchestrator.run()


__all__ = ["GenerationPipeline", "STAGE_ORDER"]
