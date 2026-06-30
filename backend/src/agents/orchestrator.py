"""OrchestratorAgent — ReAct-driven PPT generation.

The orchestrator is a real AgentScope 2.0 ReAct agent. The LLM
receives the user's request, then decides which tools to call
(``plan_outline`` → ``enrich_points`` → ``render_svg_batch`` (×N) →
``package_pptx``) and in which order. All LLM traffic flows
through the ``ReActAgent.invoke()`` loop so the middleware chain
(trace / PII / behavior) applies to every call (Constitution §I/§V).

The orchestrator is responsible for:

  * Building the LLM-backed ``ReActAgent`` with all generation tools
  * Setting the goal/seed prompt (page count, style, communication mode)
  * Driving the ReAct loop (with a generous step cap)
  * Persisting intermediate state to ``GenerationTask.rendered_slides``
    so a worker restart can resume from the last successful batch
  * Reporting final status back to the task row

Design notes:

  * We do NOT bypass the LLM with a hard-coded 4-stage harness.
    The ``HarnessAgent`` still exists for unit tests but is no
    longer the production path.
  * The "page count" hint we pass to the LLM is a soft constraint;
    the LLM is free to adjust (within a configurable ±20% range)
    if it decides the prompt needs more or fewer slides.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.agent_tools import (
    TOOL_DISPATCH,
    ToolContext,
    build_tool_schemas,
    extract_page_count,
)
from src.agents.llm_adapter import ReactLLMAdapter
from src.core.config import settings
from src.core.observability import get_logger
from src.db.models import GenerationTask, TaskStage, TaskStatus
from src.integrations.agentscope_compat import ReActAgent
from src.scheduler.queue import publish_ws_event
from src.services.generation.llm_client import LLMClient

logger = get_logger("orchestrator")

# Maximum number of ReAct steps before the loop gives up.
# Each tool call ≈ one step. Worst case: 1 plan + 1 points +
# ceil(N/5) render batches + 1 pptx + retries ≈ 4 + N/5 + 5
# 50 pages → ~19 steps; 16 is too tight, 32 covers it.
MAX_REACT_STEPS = 32


# ─────────────────────────────────────────────────────────────────────
# Middleware: trace → DB + WebSocket
# ─────────────────────────────────────────────────────────────────────
async def _trace_middleware(event_name: str, payload: dict[str, Any]) -> None:
    """Persist agent events to the trace_stages table / WS bus.

    Lightweight events go to the WS bus; expensive ones
    (``react.step``) are debounced by the worker.
    """
    if event_name in {"tool_invocation", "tool_result", "tool_error", "react.final", "react.max_steps"}:
        task_id = payload.get("task_id") or payload.get("name")
        if task_id:
            try:
                await publish_ws_event(
                    f"task:{task_id}",
                    {
                        "type": f"agent.{event_name}",
                        "ts": datetime.now(timezone.utc).isoformat(),
                        **payload,
                    },
                )
            except Exception as e:  # pragma: no cover - WS is best-effort
                logger.warning("trace_ws_emit_failed", error=str(e))


# ─────────────────────────────────────────────────────────────────────
# Orchestrator
# ─────────────────────────────────────────────────────────────────────
class OrchestratorAgent:
    """Real ReAct agent orchestrator (Constitution §I, §V).

    Replaces the prior fixed-harness design. The LLM decides the
    tool call order; we just hand it the toolset and the goal.
    """

    def __init__(
        self,
        session: AsyncSession,
        task: GenerationTask,
    ) -> None:
        self.session = session
        self.task = task

        # Tool schemas visible to the LLM
        self._tool_schemas = build_tool_schemas()

    # ── Public entry point used by the worker ───────────────────
    async def run(self) -> None:
        """Execute the agent loop for a single task."""
        # Mark task running
        self.task.status = TaskStatus.running
        self.task.started_at = datetime.now(timezone.utc)
        self.task.current_stage = TaskStage.outline
        await self.session.commit()
        await self._emit("agent.started", stage="outline")

        # Build the LLM client (async, uses user credential)
        llm = await LLMClient.from_user_credential(
            self.session, str(self.task.owner_id)
        )
        adapter = ReactLLMAdapter(llm)

        # Compose tool context
        ctx = ToolContext(
            session=self.session,
            task=self.task,
            llm=llm,
            parallelism=settings.react_svg_parallelism,
            batch_size=settings.react_svg_batch_size,
            on_stage_change=self._set_stage,
        )

        # Build the ReAct agent
        # Middleware order (Constitution §V): PII → Trace → Behavior
        # PIIMiddleware.pre_invoke / BehaviorMiddleware have richer
        # signatures; we adapt them to the (event_name, payload)
        # contract expected by ReActAgent middleware.
        from src.agents.middleware.behavior_middleware import BehaviorMiddleware
        from src.agents.middleware.pii_middleware import PIIMiddleware

        pii_mw = PIIMiddleware()
        behavior_mw = BehaviorMiddleware()

        async def _pii_middleware(event_name: str, payload: dict[str, Any]) -> None:
            """PII redaction on outgoing LLM prompts only."""
            if event_name != "react.step":
                return
            try:
                result = pii_mw._detector.detect(payload.get("user_prompt", ""))
                if result.has_pii:
                    logger.info(
                        "pii_redact_in_react_step",
                        field_count=len({h.field for h in result.hits}),
                    )
            except Exception as e:  # pragma: no cover
                logger.warning("pii_middleware_failed", error=str(e))

        async def _behavior_middleware(event_name: str, payload: dict[str, Any]) -> None:
            """Behavior preference tracking — fire-and-forget metrics."""
            if event_name != "tool_invocation":
                return
            try:
                behavior_mw.record_applied_count += 1  # type: ignore[attr-defined]
            except AttributeError:
                pass

        agent = ReActAgent(
            name=f"pptagent_react_{self.task.id}",
            tools=dict(TOOL_DISPATCH),  # function-style: ctx is passed in invoke()
            model=adapter,
            system_prompt=_build_system_prompt(),
            max_steps=MAX_REACT_STEPS,
            middleware=[_pii_middleware, _trace_middleware, _behavior_middleware],
        )

        # Goal prompt — the LLM reads this and decides which tools to call
        goal = _build_goal_prompt(self.task)

        logger.info(
            "orchestrator_run_start",
            task_id=str(self.task.id),
            page_count=extract_page_count(self.task.prompt),
        )

        try:
            result = await agent.invoke(goal, context=ctx, extra_schemas=self._tool_schemas)
        except Exception as e:
            logger.exception("orchestrator_run_failed", task_id=str(self.task.id))
            await self._fail(str(e))
            return

        # The agent's ReAct loop ends when the LLM emits a "final"
        # answer (or hits max_steps). We expect the final answer to
        # reference a ``package_pptx`` observation, but the agent
        # may have ended without packaging (e.g. mid-flow failure).
        await self._finalize(result)

    # ── Finalize: collect the rendered slides, package PPTX, score ──
    async def _finalize(self, result: dict[str, Any]) -> None:
        rendered = self.task.rendered_slides or []
        if not rendered:
            # No slides were rendered. Surface a clear error.
            await self._fail("agent finished without rendering any slides")
            return

        # If the LLM didn't call package_pptx itself, do it now.
        if not self.task.result_pptx_path:
            await self._auto_package(rendered)

        if not self.task.result_pptx_path:
            await self._fail("packaging failed — no result_pptx_path produced")
            return

        # Mark success
        self.task.status = TaskStatus.success
        self.task.finished_at = datetime.now(timezone.utc)
        self.task.current_stage = None
        await self._emit(
            "agent.finalized",
            slide_count=len(rendered),
            pptx_path=self.task.result_pptx_path,
        )

        # Style fit scoring
        try:
            from src.services.scoring.font_scorer import FontScorer
            from src.services.scoring.layout_scorer import LayoutScorer
            from src.services.scoring.palette_scorer import PaletteScorer

            layout = await LayoutScorer(self.session).score(task_id=self.task.id)
            palette = await PaletteScorer(self.session).score(task_id=self.task.id)
            font = await FontScorer(self.session).score(task_id=self.task.id)
            self.task.style_fit_score = {
                "layout": layout,
                "palette": palette,
                "font": font,
                "overall": (layout + palette + font) / 3,
            }
        except Exception as e:  # pragma: no cover
            logger.warning("scoring_failed", error=str(e))

        await self.session.commit()
        logger.info(
            "orchestrator_run_done",
            task_id=str(self.task.id),
            slide_count=len(rendered),
            stopped_reason=result.get("stopped_reason"),
        )

    async def _auto_package(self, rendered: list[dict[str, Any]]) -> None:
        """Run the PPTX render tool directly (LLM fallback).

        Build the notes map from each slide's ``notes`` field so the
        fallback packaging path preserves speaker notes the same way
        the LLM-driven ``package_pptx`` call would.
        """
        from src.agents.agent_tools import tool_package_pptx

        llm = await LLMClient.from_user_credential(
            self.session, str(self.task.owner_id)
        )
        ctx = ToolContext(
            session=self.session,
            task=self.task,
            llm=llm,
            on_stage_change=self._set_stage,
        )
        notes_map = {
            str(s.get("order", i + 1)): s.get("notes", "") or ""
            for i, s in enumerate(rendered)
            if s.get("notes")
        }
        try:
            payload = await tool_package_pptx(
                ctx,
                slides=rendered,
                notes=notes_map or None,
            )
            self.task.result_pptx_path = payload.get("pptx_path")
            self.task.current_stage = None
        except Exception as e:
            logger.exception("auto_package_failed", error=str(e))
            self.task.error_message = f"package_pptx failed: {e!s}"[:2000]

    # ── Helpers ────────────────────────────────────────────────
    async def _set_stage(self, stage: TaskStage) -> None:
        """Update ``current_stage`` and persist (used by tools via ctx).

        Called by tools (plan_outline / enrich_points / render_svg_batch /
        package_pptx) so the DB row reflects live progress, not just the
        starting ``outline`` snapshot.
        """
        if self.task.current_stage == stage:
            return
        self.task.current_stage = stage
        try:
            await self.session.commit()
        except Exception as e:  # pragma: no cover - best-effort
            logger.warning("set_stage_commit_failed", stage=stage.value, error=str(e))

    async def _fail(self, error: str) -> None:
        self.task.status = TaskStatus.failed
        self.task.finished_at = datetime.now(timezone.utc)
        self.task.error_message = error[:2000]
        await self.session.commit()
        await self._emit("agent.failed", error=error)

    async def _emit(self, event_type: str, **payload: Any) -> None:
        """Publish a WebSocket event. Best-effort (see ToolContext.emit)."""
        try:
            await publish_ws_event(
                f"task:{self.task.id}",
                {
                    "type": event_type,
                    "task_id": str(self.task.id),
                    "ts": datetime.now(timezone.utc).isoformat(),
                    **payload,
                },
            )
        except RuntimeError as e:
            if "not initialized" not in str(e):
                raise
            logger.warning("ws_emit_skipped_no_redis", event_type=event_type, error=str(e))


# ─────────────────────────────────────────────────────────────────────
# Prompt construction
# ─────────────────────────────────────────────────────────────────────
def _build_system_prompt() -> str:
    """System prompt for the LLM that drives the ReAct loop.

    The LLM is told:
      1. the high-level goal
      2. the available tools (rendered by ``build_tool_schemas``)
      3. the optimal strategy (plan → enrich → render in chunks → pack)
      4. the constraint to keep using tool calls until PPTX is packed
    """
    return (
        "You are PPTagent, a ReAct-style AI that generates complete "
        "PowerPoint decks from a one-line user prompt.\n\n"
        "Your job: given the user's prompt, call tools in a sensible "
        "order to produce a finished PPTX file. You MUST use tool "
        "calls — never answer with plain text alone.\n\n"
        "Recommended tool order (deviate only if the user prompt or "
        "tool errors justify it):\n"
        "  1) plan_outline          — produce the slide titles + types\n"
        "  2) enrich_points         — add bullet_points + speaker notes\n"
        "  3) render_svg_batch      — call repeatedly until ALL slides are rendered\n"
        "  4) package_pptx          — package the rendered slides into the final PPTX\n\n"
        "If a render_svg_batch call returns slides with "
        "\"used_fallback\": true, immediately call redo_slide for "
        "each of those slides before moving on.\n\n"
        "Important rules:\n"
        "  - The goal prompt will tell you the page count. Honour it.\n"
        "  - render_svg_batch takes at most "
        f"{settings.react_svg_batch_size} slides per call; for longer "
        "decks, call it multiple times with consecutive slide ranges.\n"
        "  - Always include a speaker-notes map in package_pptx if the\n"
        "    enrich_points output provided notes.\n"
        "  - When you have finished, respond with a single JSON object\n"
        "    {\"type\": \"final\", \"content\": \"<short summary>\"}.\n"
    )


def _build_goal_prompt(task: GenerationTask) -> str:
    """The user-facing goal passed to the ReAct loop."""
    page_count = extract_page_count(task.prompt or "")
    pieces: list[str] = [
        f"Generate a {page_count}-slide PowerPoint deck.",
        f"User prompt: {task.prompt!r}",
    ]
    if task.visual_style:
        pieces.append(f"Visual style: {task.visual_style}")
    if task.communication_mode:
        pieces.append(f"Communication mode: {task.communication_mode}")
    if task.source_file_ids:
        pieces.append(
            f"Source material available: {len(task.source_file_ids)} parsed document(s). "
            "Use query_knowledge_base to pull relevant context."
        )
    pieces.append(
        "You MUST call plan_outline first, then enrich_points, then "
        "render_svg_batch in chunks of "
        f"{settings.react_svg_batch_size}, then package_pptx. "
        "When the PPTX is packaged, respond with a final JSON message."
    )
    return "\n".join(pieces)


__all__ = ["OrchestratorAgent"]
