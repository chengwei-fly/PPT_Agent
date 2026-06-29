"""OrchestratorAgent — drives the 4-stage pipeline.

Wraps the AgentScope `HarnessAgent` (via `src.integrations.agentscope_compat`).
The four pipeline stages (`outline → points → svg → pptx`) are registered as
`HarnessAgent` stages; the harness runs them in order, stops on first failure,
and records per-stage timing into `state['_harness_trace']` — which the
persistence layer writes to the `trace_stages` table.
"""

from __future__ import annotations

from typing import Any

from src.core.observability import get_logger
from src.integrations.agentscope_compat import HarnessAgent
from src.services.generation.pipeline import GenerationPipeline

logger = get_logger("orchestrator")


class OrchestratorAgent:
    """PPTagent's fixed-pipeline orchestrator.

    Stages (registered below):
        1. outline  — plan slide-by-slide structure
        2. points   — extract bullet content per slide
        3. svg      — render per-slide SVG payloads
        4. pptx     — package SVGs into a final PPTX (via pptx_renderer tool)
    """

    def __init__(self) -> None:
        self._harness = HarnessAgent(name="pptagent_orchestrator")
        self._register_stages()

    def _register_stages(self) -> None:
        self._harness.add_stage("outline", self._stage_outline)
        self._harness.add_stage("points", self._stage_points)
        self._harness.add_stage("svg", self._stage_svg)
        self._harness.add_stage("pptx", self._stage_pptx)

    @staticmethod
    async def _stage_outline(state: dict[str, Any]) -> dict[str, Any]:
        from src.db.session import get_session_factory

        task_id = state["task_id"]
        factory = get_session_factory()
        async with factory() as session:
            pipeline = GenerationPipeline(session, task_id)
            await pipeline._run_outline(state)
        return {"outline_done": True}

    @staticmethod
    async def _stage_points(state: dict[str, Any]) -> dict[str, Any]:
        from src.db.session import get_session_factory

        task_id = state["task_id"]
        factory = get_session_factory()
        async with factory() as session:
            pipeline = GenerationPipeline(session, task_id)
            await pipeline._run_points(state)
        return {"points_done": True}

    @staticmethod
    async def _stage_svg(state: dict[str, Any]) -> dict[str, Any]:
        from src.db.session import get_session_factory

        task_id = state["task_id"]
        factory = get_session_factory()
        async with factory() as session:
            pipeline = GenerationPipeline(session, task_id)
            await pipeline._run_svg(state)
        return {"svg_done": True}

    @staticmethod
    async def _stage_pptx(state: dict[str, Any]) -> dict[str, Any]:
        from src.db.session import get_session_factory

        task_id = state["task_id"]
        factory = get_session_factory()
        async with factory() as session:
            pipeline = GenerationPipeline(session, task_id)
            await pipeline._run_pptx(state)
        return {"pptx_done": True}

    async def run(self, task_id: str) -> dict[str, Any]:
        """Execute the harness for a single task.

        Returns the final state (including `_harness_trace`) so the
        caller can persist per-stage status.
        """
        logger.info("orchestrator_run_start", task_id=task_id)
        state = await self._harness.invoke({"task_id": task_id})
        logger.info(
            "orchestrator_run_done",
            task_id=task_id,
            stages=[e.get("name") for e in state.get("_harness_trace", [])],
        )
        return state

    # ── Direct (non-harness) entry point used by the worker ──
    # Kept for back-compat with code that still calls
    # `OrchestratorAgent().run(task_id)` and expects a coroutine.
    async def run_direct(self, task_id: str) -> None:
        from src.db.session import get_session_factory

        factory = get_session_factory()
        async with factory() as session:
            pipeline = GenerationPipeline(session, task_id)
            await pipeline.run()


__all__ = ["OrchestratorAgent"]
