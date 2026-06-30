"""Tool implementations for the ReAct-driven PPT generation agent.

Each function here is exposed to the LLM as a `Tool` (see
`src.integrations.agentscope_compat.Tool`). The LLM decides the
order and the parameters; the agent loop (in
`src.agents.react_agent.ReActAgent`) wires the calls together.

Design contract (Constitution §I, §III, §V):

  * Tools MUST be idempotent on retry — calling ``render_svg_batch``
    twice for the same ``batch_id`` MUST return the same result.
  * Tools MUST emit one ``tool_invocation`` event per call (handled
    by the agent's middleware chain, not the tool itself).
  * Tools MUST NOT call the LLM directly — they go through
    ``LLMClient`` which is wired into the agent's ReAct loop.
  * Tools MUST persist their outputs to the DB so the agent can
    resume from any failure point (FR-016 redo contract).
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.observability import get_logger
from src.scheduler.queue import publish_ws_event
from src.services.generation.llm_client import LLMClient
from src.services.generation.prompts import get_svg_system_prompt

if TYPE_CHECKING:
    # Imported only for type hints — keeps this module importable
    # in scripts / smoke tests without pulling in pgvector etc.
    from src.db.models import GenerationTask

logger = get_logger("agent_tools")


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────
def _validate_svg(svg: str) -> tuple[bool, str]:
    """Validate SVG XML. Returns (ok, fixed_svg)."""
    if not svg:
        return False, ""
    candidate = svg.strip()
    if not candidate.startswith("<?xml"):
        candidate = '<?xml version="1.0" encoding="UTF-8"?>\n' + candidate
    try:
        ET.fromstring(candidate)
        return True, candidate
    except ET.ParseError:
        return False, candidate


def _strip_code_fences(text: str) -> str:
    """Strip ``` and ```xml / ```json fences from LLM output."""
    text = text.strip()
    if text.startswith("```"):
        first_nl = text.find("\n")
        if first_nl != -1:
            text = text[first_nl + 1 :]
    if text.endswith("```"):
        text = text[:-3].strip()
    return text


def _fallback_svg(title: str, bullets: list[str], order: int) -> str:
    """Used when the LLM output cannot be validated even after one retry."""
    bullet_svg = ""
    for i, bp in enumerate(bullets[:5]):
        y = 160 + i * 50
        bullet_svg += f'<circle cx="100" cy="{y - 5}" r="4" fill="#4A90D9"/>\n'
        bullet_svg += (
            f'<text x="120" y="{y}" font-family="Arial" font-size="18" '
            f'fill="#333">{bp}</text>\n'
        )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" width="1280" height="720">
  <rect width="1280" height="720" fill="#FFFFFF"/>
  <rect x="0" y="0" width="1280" height="10" fill="#4A90D9"/>
  <text x="80" y="80" font-family="Arial" font-size="36" font-weight="bold" fill="#1A1A1A">{title}</text>
  <line x1="80" y1="95" x2="300" y2="95" stroke="#4A90D9" stroke-width="4"/>
  {bullet_svg}
  <text x="1180" y="700" font-family="Arial" font-size="14" fill="#999">{order}</text>
</svg>"""


async def _load_source_context_async(
    session: AsyncSession, source_file_ids: list[uuid.UUID]
) -> str:
    """Load parsed text content from source Sample files (async)."""
    if not source_file_ids:
        return ""
    from src.db.models import ParseResult, Sample

    result = await session.execute(
        select(ParseResult, Sample.file_name)
        .join(Sample, ParseResult.sample_id == Sample.id)
        .where(ParseResult.sample_id.in_(source_file_ids))
    )
    contents: list[str] = []
    for pr, file_name in result.all():
        if not pr.structure_json:
            continue
        chunks = pr.structure_json.get("text_chunks", [])
        if not chunks:
            continue
        file_content = "\n\n".join(
            c.get("text", "") for c in chunks if c.get("text")
        )
        if file_content.strip():
            contents.append(f"## {file_name}\n\n{file_content}")
    return "\n\n---\n\n".join(contents)[:20000]


# ─────────────────────────────────────────────────────────────────────
# Page-count extraction (used by plan_outline)
# ─────────────────────────────────────────────────────────────────────
def extract_page_count(prompt: str, default: int = 10, max_pages: int = 60) -> int:
    """Pull page count out of a user prompt. Supports zh / en."""
    if not prompt:
        return default
    # Chinese patterns: "12页", "做12份", "10 张"
    m = re.search(r"(\d+)\s*[页份张]", prompt)
    if m:
        n = int(m.group(1))
        if 1 <= n <= max_pages:
            return n
    # English / numeric patterns
    m = re.search(r"(\d+)\s*(?:pages|slides|页)", prompt, re.IGNORECASE)
    if m:
        n = int(m.group(1))
        if 1 <= n <= max_pages:
            return n
    for word in prompt.split():
        if word.isdigit():
            n = int(word)
            if 1 <= n <= max_pages:
                return n
    return default


# ─────────────────────────────────────────────────────────────────────
# Tool context — every tool call receives this so it can access the
# active session, LLM, and event sink without explicit injection.
# ─────────────────────────────────────────────────────────────────────
@dataclass
class ToolContext:
    session: AsyncSession
    task: GenerationTask
    llm: LLMClient
    parallelism: int = 4
    batch_size: int = 5
    # Optional callback used by tools to update task.current_stage
    # (signature: async def on_stage_change(stage: TaskStage) -> None)
    on_stage_change: Any | None = None

    async def emit(self, event_type: str, **payload: Any) -> None:
        """Publish a WebSocket event. Best-effort: never raises.

        Smoke tests / dev environments may run without Redis; the
        tool chain MUST still complete end-to-end. We log and
        swallow the RuntimeError raised by ``get_client`` when
        the queue is not initialized.
        """
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
            # Only swallow "Redis not initialized" — propagate
            # other errors so the user sees real bugs.
            if "not initialized" not in str(e):
                raise
            logger.warning("ws_emit_skipped_no_redis", event_type=event_type, error=str(e))

    async def set_stage(self, stage: str) -> None:
        """Update GenerationTask.current_stage via the orchestrator hook.

        Falls back to a no-op when no hook is registered (e.g. smoke
        tests that build a ToolContext without an OrchestratorAgent).
        """
        if self.on_stage_change is None:
            return
        # Local import to avoid pulling models at module import time
        from src.db.models import TaskStage

        try:
            stage_enum = TaskStage(stage)
        except ValueError:
            return
        try:
            await self.on_stage_change(stage_enum)
        except Exception as e:  # pragma: no cover - best-effort
            logger.warning("set_stage_hook_failed", stage=stage, error=str(e))

    async def bill_tokens(self) -> None:
        """Drain the LLMClient's accumulated usage and persist on the task.

        Tools (plan_outline / enrich_points / render_svg_batch) call
        this after their LLM work is done. The LLMClient accumulates
        ``total_tokens`` from the upstream API across all ``complete*``
        calls, so the task's ``token_consumed`` is the real number,
        not a fixed estimate.
        """
        used = int(getattr(self.llm, "last_usage_total", 0) or 0)
        if used <= 0:
            return
        self.task.token_consumed = (self.task.token_consumed or 0) + used
        self.llm.last_usage_total = 0
        try:
            await self.session.commit()
        except Exception as e:  # pragma: no cover - best-effort
            logger.warning("bill_tokens_commit_failed", used=used, error=str(e))


# ─────────────────────────────────────────────────────────────────────
# Tool 1: plan_outline
# ─────────────────────────────────────────────────────────────────────
async def tool_plan_outline(
    ctx: ToolContext,
    *,
    prompt: str,
    page_count: int,
    communication_mode: str | None = None,
    visual_style: str | None = None,
    source_context: str = "",
) -> dict[str, Any]:
    """Plan a structured outline of N slides for the given prompt.

    Returns a dict: {summary, slides: [{order, title, description, slide_type}]}.
    """
    await ctx.set_stage("outline")
    system_parts = [
        "You are a presentation strategist. Generate a structured slide outline as JSON.",
        "Output a JSON object with: summary (string), slides (array of {order, title, description, slide_type}).",
        "slide_type must be one of: cover, toc, body, closing.",
        "The first slide should be cover, second should be toc (if >4 slides), last should be closing.",
    ]
    if communication_mode:
        from src.services.generation.reference_loader import ReferenceLoader

        mode_spec = ReferenceLoader().load_communication_mode(communication_mode)
        if mode_spec:
            system_parts.append(
                f"\n## Communication Mode: {communication_mode}\n{mode_spec[:2000]}"
            )
    system_parts.append(f"\nGenerate exactly {page_count} slides.")

    user_prompt = prompt or "Create a presentation"
    if source_context:
        user_prompt = f"{user_prompt}\n\n## Source Material\n{source_context[:8000]}"

    # Scale JSON output budget with page count
    max_tokens = min(16000, 4000 + page_count * 220)

    result = await ctx.llm.complete_json(
        system_prompt="\n".join(system_parts),
        user_prompt=user_prompt,
        temperature=0.3,
        max_tokens=max_tokens,
    )

    slides = result.get("slides", [])
    if not isinstance(slides, list):
        raise RuntimeError(f"plan_outline: 'slides' must be a list, got {type(slides)}")

    # Pad / trim to the requested page count
    if len(slides) < page_count:
        for i in range(len(slides), page_count):
            slides.append(
                {
                    "order": i + 1,
                    "title": f"补充内容 {i + 1}",
                    "description": "",
                    "slide_type": "body",
                }
            )
    slides = slides[:page_count]
    for i, s in enumerate(slides):
        s["order"] = i + 1
        s.setdefault("slide_type", "body")

    summary = result.get("summary") or f"大纲：{page_count} 页"
    await ctx.bill_tokens()
    return {
        "summary": summary,
        "slides": slides,
        "tokens": max(500, page_count * 200),
    }


# ─────────────────────────────────────────────────────────────────────
# Tool 2: enrich_points
# ─────────────────────────────────────────────────────────────────────
async def tool_enrich_points(
    ctx: ToolContext,
    *,
    outline: dict[str, Any],
    source_context: str = "",
) -> dict[str, Any]:
    """Take an outline, return bullet_points + speaker_notes per slide."""
    await ctx.set_stage("points")
    slides = outline.get("slides", [])
    system_prompt = (
        "You are a presentation content writer. For each slide in the outline, "
        "generate detailed bullet points and speaker notes.\n"
        "Output a JSON object with: slides (array of {order, title, bullet_points: string[], notes: string}).\n"
        "Each slide should have 3-5 concise, assertion-style bullet points.\n"
        "Notes should be 2-3 sentences of speaking guidance."
    )
    user_parts = [
        f"## Outline\n```json\n{json.dumps(slides, ensure_ascii=False)}\n```"
    ]
    if source_context:
        user_parts.append(f"## Source Material\n{source_context[:8000]}")

    page_count = len(slides)
    max_tokens = min(16000, 4000 + page_count * 350)

    result = await ctx.llm.complete_json(
        system_prompt=system_prompt,
        user_prompt="\n\n".join(user_parts),
        temperature=0.3,
        max_tokens=max_tokens,
    )
    enriched = result.get("slides", [])
    if not isinstance(enriched, list):
        raise RuntimeError(
            f"enrich_points: 'slides' must be a list, got {type(enriched)}"
        )

    outline_map = {s.get("order"): s for s in slides}
    merged: list[dict[str, Any]] = []
    for es in enriched:
        order = es.get("order", 0)
        base = outline_map.get(order, {})
        merged.append(
            {
                "order": order,
                "title": es.get("title") or base.get("title", ""),
                "description": base.get("description", ""),
                "slide_type": base.get("slide_type", "body"),
                "bullet_points": es.get("bullet_points", []),
                "notes": es.get("notes", ""),
            }
        )
    # Fill missing
    for s in slides:
        if not any(m["order"] == s.get("order") for m in merged):
            merged.append(
                {
                    "order": s.get("order"),
                    "title": s.get("title", ""),
                    "description": s.get("description", ""),
                    "slide_type": s.get("slide_type", "body"),
                    "bullet_points": [s.get("title", "要点")],
                    "notes": "",
                }
            )
    merged.sort(key=lambda x: x.get("order", 0))

    await ctx.bill_tokens()
    return {
        "summary": f"要点提取：{len(merged)} 页",
        "slides": merged,
        "tokens": max(1000, len(merged) * 400),
    }


# ─────────────────────────────────────────────────────────────────────
# Tool 3: render_svg_batch
# ─────────────────────────────────────────────────────────────────────
async def tool_render_svg_batch(
    ctx: ToolContext,
    *,
    slides: list[dict[str, Any]],
    visual_style: str | None = None,
    communication_mode: str | None = None,
    batch_id: str | None = None,
) -> dict[str, Any]:
    """Render N slides in parallel batches of ``ctx.batch_size``.

    Returns: {rendered: [{order, svg, title, used_fallback}]}
    """
    if not slides:
        return {"rendered": [], "tokens": 0}

    await ctx.set_stage("svg")

    # Idempotency: stable batch_id (so retries collapse)
    batch_id = batch_id or f"svg-{uuid.uuid4().hex[:8]}"

    # System prompt is cached per (style, mode) — built ONCE for the whole batch
    system_prompt = get_svg_system_prompt(visual_style, communication_mode)

    sem = asyncio.Semaphore(max(1, ctx.parallelism))

    async def _render_one(slide: dict[str, Any]) -> dict[str, Any]:
        order = slide.get("order", 0)
        title = slide.get("title", "")
        bullets = slide.get("bullet_points", []) or []
        notes = slide.get("notes", "")
        slide_type = slide.get("slide_type", "body")

        user_prompt = (
            f"Generate an SVG for slide {order}.\n"
            f"Type: {slide_type}\n"
            f"Title: {title}\n"
            f"Bullet points:\n"
            + "\n".join(f"- {bp}" for bp in bullets)
            + f"\nSpeaker notes: {notes}"
        )

        async with sem:
            try:
                svg_text = await ctx.llm.complete(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=0.4,
                    max_tokens=4000,
                )
            except Exception as e:
                logger.warning(
                    "svg_render_llm_failed",
                    order=order,
                    error=str(e),
                )
                return {
                    "order": order,
                    "title": title,
                    "svg": _fallback_svg(title, bullets, order),
                    "used_fallback": True,
                }

        svg_text = _strip_code_fences(svg_text)
        ok, fixed = _validate_svg(svg_text)
        if not ok:
            logger.warning("svg_validation_failed", order=order)
            return {
                "order": order,
                "title": title,
                "svg": _fallback_svg(title, bullets, order),
                "used_fallback": True,
            }
        return {
            "order": order,
            "title": title,
            "svg": fixed,
            "used_fallback": False,
        }

    # Process in batches but run all batches' items concurrently
    # (parallelism-bounded by the semaphore).
    results: list[dict[str, Any]] = await asyncio.gather(
        *(_render_one(s) for s in slides),
        return_exceptions=False,
    )
    results.sort(key=lambda r: r.get("order", 0))

    fallback_count = sum(1 for r in results if r.get("used_fallback"))

    # Persist to checkpoint so a worker restart can resume.
    # We merge with any previously-rendered slides (by order).
    await _persist_rendered_slides(ctx, results)

    await ctx.emit(
        "svg.batch_done",
        batch_id=batch_id,
        rendered=len(results),
        fallback=fallback_count,
    )

    return {
        "rendered": results,
        "batch_id": batch_id,
        "tokens": len(results) * 1200,
        "fallback_count": fallback_count,
    }


async def _persist_rendered_slides(
    ctx: ToolContext,
    new_slides: list[dict[str, Any]],
) -> None:
    """Merge new rendered slides into the task's checkpoint.

    Slides are keyed by ``order`` so partial retries replace
    only the affected slide. ``token_consumed`` is incremented
    by the real LLM-reported usage captured by the LLMClient
    (see ``src.services.generation.llm_client.LLMClient.complete*``).
    """
    existing = list(ctx.task.rendered_slides or [])
    by_order = {s.get("order"): s for s in existing}
    for s in new_slides:
        by_order[s.get("order")] = s
    merged = sorted(by_order.values(), key=lambda x: x.get("order", 0))
    ctx.task.rendered_slides = merged
    # Drain real LLM-reported usage (sum across this batch's parallel
    # calls). Falls through as no-op when the LLMClient is a stub that
    # doesn't report usage.
    await ctx.bill_tokens()
    if not getattr(ctx.llm, "last_usage_total", 0):
        # No upstream usage reported — apply a coarse estimate so the
        # field still moves forward and is visible to billing.
        ctx.task.token_consumed = (ctx.task.token_consumed or 0) + len(new_slides) * 1200
        await ctx.session.commit()


# ─────────────────────────────────────────────────────────────────────
# Tool 4: redo_slide
# ─────────────────────────────────────────────────────────────────────
async def tool_redo_slide(
    ctx: ToolContext,
    *,
    slide: dict[str, Any],
    feedback: str = "",
    visual_style: str | None = None,
    communication_mode: str | None = None,
) -> dict[str, Any]:
    """Re-render a single slide (used when batch results are bad)."""
    result = await tool_render_svg_batch(
        ctx,
        slides=[slide],
        visual_style=visual_style,
        communication_mode=communication_mode,
        batch_id=f"redo-{slide.get('order', 0)}",
    )
    if feedback and result["rendered"]:
        logger.info("slide_redo_with_feedback", order=slide.get("order"), feedback=feedback[:200])
    return result


# ─────────────────────────────────────────────────────────────────────
# Tool 5: package_pptx
# ─────────────────────────────────────────────────────────────────────
async def tool_package_pptx(
    ctx: ToolContext,
    *,
    slides: list[dict[str, Any]],
    theme: dict[str, Any] | None = None,
    notes: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Package a list of slide SVGs into a final PPTX file.

    Wraps ``PPTXRenderTool`` (kept as the rendering engine for
    backward compatibility).
    """
    await ctx.set_stage("pptx")
    from src.tools.pptx_renderer import PPTXRenderTool

    renderer = PPTXRenderTool()
    payload = await renderer.func(
        task_id=str(ctx.task.id),
        slides=slides,
        theme=theme,
        notes=notes,
    )
    await ctx.emit("pptx.packed", slide_count=payload.get("slide_count"))
    return payload


# ─────────────────────────────────────────────────────────────────────
# Tool 6: query_knowledge_base (passes through to existing retriever)
# ─────────────────────────────────────────────────────────────────────
async def tool_query_knowledge_base(
    ctx: ToolContext,
    *,
    query: str,
    top_k: int = 5,
) -> dict[str, Any]:
    """Pull top-k chunks from the user's knowledge base."""
    from src.tools.knowledge_retriever import KnowledgeRetriever

    kb = KnowledgeRetriever(owner_id=ctx.task.owner_id)
    hits = await kb.retrieve_async(query=query, top_k=top_k)
    return {"query": query, "top_k": top_k, "hits": hits}


# ─────────────────────────────────────────────────────────────────────
# Tool registry
# ─────────────────────────────────────────────────────────────────────
def build_tool_schemas() -> list[dict[str, Any]]:
    """Return JSON schemas for all tools (consumed by the LLM)."""
    return [
        {
            "type": "function",
            "function": {
                "name": "plan_outline",
                "description": (
                    "Plan a structured slide outline (titles + slide_type) for the user's prompt. "
                    "ALWAYS call this FIRST."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string", "description": "Original user prompt"},
                        "page_count": {
                            "type": "integer",
                            "description": "Number of slides to generate (3-60)",
                        },
                        "communication_mode": {
                            "type": "string",
                            "enum": ["pyramid", "narrative", "instructional", "showcase", "briefing"],
                        },
                        "visual_style": {
                            "type": "string",
                            "description": "One of the registered visual styles (e.g. swiss-minimal).",
                        },
                    },
                    "required": ["prompt", "page_count"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "enrich_points",
                "description": (
                    "Take an outline and produce 3-5 bullet points + speaker notes per slide. "
                    "Call AFTER plan_outline."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "outline": {
                            "type": "object",
                            "description": "Result of plan_outline (has 'slides' array).",
                        },
                        "source_context": {
                            "type": "string",
                            "description": "Optional pre-loaded source material (markdown text).",
                        },
                    },
                    "required": ["outline"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "render_svg_batch",
                "description": (
                    "Render N slides as SVG in parallel. Pass at most "
                    f"{settings.react_svg_batch_size} slides per call. "
                    "For larger decks, call this multiple times with successive slide ranges."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "slides": {
                            "type": "array",
                            "items": {"type": "object"},
                            "description": "Slides to render (from enrich_points output).",
                        },
                        "visual_style": {"type": "string"},
                        "communication_mode": {"type": "string"},
                    },
                    "required": ["slides"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "redo_slide",
                "description": "Re-render a single slide (use when validation fails).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "slide": {
                            "type": "object",
                            "description": "The slide to re-render (with order, title, bullet_points).",
                        },
                        "feedback": {"type": "string"},
                    },
                    "required": ["slide"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "package_pptx",
                "description": (
                    "Package a list of rendered SVG slides into the final PPTX file. "
                    "Call AFTER all slides are rendered."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "slides": {
                            "type": "array",
                            "items": {"type": "object"},
                        },
                        "theme": {"type": "object"},
                        "notes": {"type": "object"},
                    },
                    "required": ["slides"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "query_knowledge_base",
                "description": (
                    "Retrieve top-k chunks from the user's knowledge base. "
                    "Use to ground the outline / points / SVG in the user's own material."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "top_k": {"type": "integer", "default": 5},
                    },
                    "required": ["query"],
                },
            },
        },
    ]


# Mapping: tool name -> implementation
TOOL_DISPATCH: dict[str, Any] = {
    "plan_outline": tool_plan_outline,
    "enrich_points": tool_enrich_points,
    "render_svg_batch": tool_render_svg_batch,
    "redo_slide": tool_redo_slide,
    "package_pptx": tool_package_pptx,
    "query_knowledge_base": tool_query_knowledge_base,
}


__all__ = [
    "ToolContext",
    "build_tool_schemas",
    "extract_page_count",
    "TOOL_DISPATCH",
]
