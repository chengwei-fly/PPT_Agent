"""Generation pipeline (T040) — orchestrates 4 stages with trace middleware."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.middleware.trace_middleware import TraceMiddleware
from src.core.observability import get_logger
from src.db.models import (
    GenerationMode,
    GenerationTask,
    StageStatus,
    TaskStage,
    TaskStatus,
)
from src.scheduler.queue import publish_ws_event
from src.services.scoring.font_scorer import FontScorer
from src.services.scoring.layout_scorer import LayoutScorer
from src.services.scoring.palette_scorer import PaletteScorer
from src.tools.svg2pptx import SVG2PPTXTool

logger = get_logger("pipeline")

STAGE_ORDER = [TaskStage.outline, TaskStage.points, TaskStage.svg, TaskStage.pptx]


class GenerationPipeline:
    """Drives a task through outline → points → svg → pptx."""

    def __init__(self, session: AsyncSession, task_id: str) -> None:
        self.session = session
        self.task_id = uuid.UUID(task_id)
        self.trace = TraceMiddleware(session)
        self.svg2pptx = SVG2PPTXTool()

    async def run(self) -> None:
        task = (
            await self.session.execute(
                select(GenerationTask).where(GenerationTask.id == self.task_id)
            )
        ).scalar_one_or_none()
        if not task:
            logger.error("task_not_found", task_id=str(self.task_id))
            return

        task.status = TaskStatus.running
        task.started_at = datetime.now(timezone.utc)
        task.current_stage = STAGE_ORDER[0]
        await self.session.commit()

        # ── Select stage methods based on mode ─────────────────────
        is_general = task.mode == GenerationMode.general

        # ── Stage 1: outline ───────────────────────────────────────
        outline_stage = await self.trace.on_stage_start(
            task_id=task.id,
            stage_name="outline",
            stage_order=1,
            input_summary=task.prompt[:200],
            referenced_sample_ids=list(task.sample_snapshot_ids),
        )
        await self._emit_ws(task.id, "outline", "running")
        try:
            if is_general:
                outline_payload = await self._stage_outline_general(task)
            else:
                outline_payload = await self._stage_outline(task)
            await self.trace.on_stage_finish(
                outline_stage, output_summary=outline_payload["summary"]
            )
            task.token_consumed += outline_payload["tokens"]
        except Exception as e:
            await self.trace.on_stage_finish(
                outline_stage, output_summary="", status=StageStatus.failed, error_message=str(e)
            )
            await self._fail_task(task, str(e))
            return
        await self._emit_ws(task.id, "outline", "success")

        # ── Stage 2: points ───────────────────────────────────────
        points_stage = await self.trace.on_stage_start(
            task_id=task.id,
            stage_name="points",
            stage_order=2,
            input_summary=outline_payload["summary"],
        )
        await self._emit_ws(task.id, "points", "running")
        try:
            if is_general:
                points_payload = await self._stage_points_general(outline_payload, task)
            else:
                points_payload = await self._stage_points(outline_payload)
            await self.trace.on_stage_finish(points_stage, output_summary=points_payload["summary"])
            task.token_consumed += points_payload["tokens"]
        except Exception as e:
            await self.trace.on_stage_finish(
                points_stage, output_summary="", status=StageStatus.failed, error_message=str(e)
            )
            await self._fail_task(task, str(e))
            return
        await self._emit_ws(task.id, "points", "success")

        # ── Stage 3: svg ──────────────────────────────────────────
        svg_stage = await self.trace.on_stage_start(
            task_id=task.id,
            stage_name="svg",
            stage_order=3,
            input_summary=points_payload["summary"],
        )
        await self._emit_ws(task.id, "svg", "running")
        try:
            if is_general:
                svg_payload = await self._stage_svg_general(points_payload, task)
            else:
                svg_payload = await self._stage_svg(points_payload)
            await self.trace.on_stage_finish(svg_stage, output_summary=svg_payload["summary"])
            task.token_consumed += svg_payload["tokens"]
        except Exception as e:
            await self.trace.on_stage_finish(
                svg_stage, output_summary="", status=StageStatus.failed, error_message=str(e)
            )
            await self._fail_task(task, str(e))
            return
        await self._emit_ws(task.id, "svg", "success")

        # ── Stage 4: pptx ─────────────────────────────────────────
        pptx_stage = await self.trace.on_stage_start(
            task_id=task.id, stage_name="pptx", stage_order=4, input_summary=svg_payload["summary"]
        )
        await self._emit_ws(task.id, "pptx", "running")
        try:
            pptx_payload = await self.svg2pptx.func(
                task_id=str(task.id), slides=svg_payload["slides"]
            )
            await self.trace.on_stage_finish(
                pptx_stage,
                output_summary=f"PPTX: {pptx_payload['slide_count']} slides in {pptx_payload['duration_ms']}ms",
            )
        except Exception as e:
            await self.trace.on_stage_finish(
                pptx_stage, output_summary="", status=StageStatus.failed, error_message=str(e)
            )
            await self._fail_task(task, str(e))
            return
        await self._emit_ws(task.id, "pptx", "success")

        # ── Mark success + compute style fit score ────────────────
        task.result_pptx_path = pptx_payload["pptx_path"]
        task.status = TaskStatus.success
        task.finished_at = datetime.now(timezone.utc)
        task.current_stage = None
        # Compute scoring (FR-028 / SC-002)
        layout_score = await LayoutScorer(self.session).score(task_id=task.id)
        palette_score = await PaletteScorer(self.session).score(task_id=task.id)
        font_score = await FontScorer(self.session).score(task_id=task.id)
        task.style_fit_score = {
            "layout": layout_score,
            "palette": palette_score,
            "font": font_score,
            "overall": (layout_score + palette_score + font_score) / 3,
        }
        await self.session.commit()
        await self._emit_ws(
            task.id, "success", "success", extra={"result_pptx_path": task.result_pptx_path}
        )

    # ── Stage impls ─────────────────────────────────────────────────
    async def _stage_outline(self, task: GenerationTask) -> dict[str, Any]:
        """Outline stage — produces a structured slide-by-slide outline.

        Parses the user prompt to extract topic and page count, then generates
        a structured outline with section titles and brief descriptions.
        Full impl: invoke LLM via ReActAgent + knowledge retriever.
        """
        prompt = task.prompt or "汇报"
        # Extract page count from prompt (default 10)
        # Handles Chinese patterns like "12页", "做12份", "10 页"
        n_pages = 10
        page_match = re.search(r"(\d+)\s*[页份张]", prompt)
        if page_match:
            extracted = int(page_match.group(1))
            if 3 <= extracted <= 30:
                n_pages = extracted
        else:
            for word in prompt.split():
                if word.isdigit() and 3 <= int(word) <= 30:
                    n_pages = int(word)
                    break

        # Generate section titles based on prompt keywords
        base_sections = [
            "封面",
            "目录",
            "背景与目标",
            "现状分析",
            "核心方案",
            "实施计划",
            "资源配置",
            "风险管控",
            "预期成果",
            "总结与展望",
        ]
        # Extend or trim to match n_pages
        while len(base_sections) < n_pages:
            base_sections.insert(-1, f"补充内容 {len(base_sections) - 2}")
        base_sections = base_sections[:n_pages]

        slides = [
            {
                "order": i + 1,
                "title": title,
                "description": f"基于「{prompt[:50]}」生成的第 {i + 1} 页",
            }
            for i, title in enumerate(base_sections)
        ]

        summary = f"大纲：{n_pages} 页，主题「{prompt[:30]}」"
        tokens = max(500, n_pages * 150)  # estimate based on page count

        return {"summary": summary, "slides": slides, "tokens": tokens}

    async def _stage_points(self, outline: dict) -> dict[str, Any]:
        """Points stage — generates bullet points for each slide.

        Takes the outline and produces detailed bullet points with key data
        points and supporting evidence for each section.
        Full impl: invoke LLM with knowledge context.
        """
        slides = outline.get("slides", [])
        enriched = []
        for slide in slides:
            title = slide.get("title", "")
            points = [
                f"{title}的核心要点",
                "数据支撑与案例分析",
                "关键指标与里程碑",
            ]
            enriched.append(
                {
                    **slide,
                    "bullet_points": points,
                    "notes": f"详细展开「{title}」的论述",
                }
            )

        summary = f"要点提取：{len(slides)} 页，每页 3-5 个要点"
        tokens = max(1000, len(slides) * 300)

        return {"summary": summary, "slides": enriched, "tokens": tokens}

    async def _stage_svg(self, points: dict) -> dict[str, Any]:
        """SVG stage — renders each slide as SVG.

        Converts bullet points into structured SVG slides with proper layout,
        typography, and color scheme.
        Full impl: invoke SVG rendering agent with style reference.
        """
        slides = points.get("slides", [])
        svg_slides = []
        for slide in slides:
            title = slide.get("title", "")
            bullets = slide.get("bullet_points", [])
            order = slide.get("order", 1)

            # Build a structured SVG with title and bullet points
            bullet_svg = ""
            for i, bp in enumerate(bullets[:5]):
                y = 120 + i * 40
                bullet_svg += f'<circle cx="80" cy="{y - 5}" r="3" fill="#4A90D9"/>'
                bullet_svg += f'<text x="95" y="{y}" font-family="Microsoft YaHei" font-size="14" fill="#333">{bp}</text>'

            svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 540" width="960" height="540">
  <rect width="960" height="540" fill="#FFFFFF"/>
  <rect x="0" y="0" width="960" height="8" fill="#4A90D9"/>
  <text x="60" y="60" font-family="Microsoft YaHei" font-size="28" font-weight="bold" fill="#1A1A1A">{title}</text>
  <line x1="60" y1="75" x2="200" y2="75" stroke="#4A90D9" stroke-width="3"/>
  {bullet_svg}
  <text x="860" y="520" font-family="Microsoft YaHei" font-size="12" fill="#999">{order}</text>
</svg>"""
            svg_slides.append({"order": order, "svg": svg, "title": title})

        summary = f"SVG 渲染：{len(svg_slides)} 张幻灯片"
        tokens = max(2000, len(svg_slides) * 500)

        return {"summary": summary, "slides": svg_slides, "tokens": tokens}

    # ── General mode stage implementations (LLM-powered) ──────────
    async def _stage_outline_general(self, task: GenerationTask) -> dict[str, Any]:
        """LLM-powered outline stage for general mode."""
        from src.services.generation.llm_client import LLMClient
        from src.services.generation.reference_loader import ReferenceLoader

        llm = await LLMClient.from_user_credential(self.session, str(task.owner_id))
        refs = ReferenceLoader()

        # Build system prompt
        system_parts = [
            "You are a presentation strategist. Generate a structured slide outline as JSON.",
            "Output a JSON object with: summary (string), slides (array of {order, title, description, slide_type}).",
            "slide_type must be one of: cover, toc, body, closing.",
            "The first slide should be cover, second should be toc (if >4 slides), last should be closing.",
        ]

        # Add communication mode context if specified
        if task.communication_mode:
            mode_spec = refs.load_communication_mode(task.communication_mode)
            if mode_spec:
                system_parts.append(
                    f"\n## Communication Mode: {task.communication_mode}\n{mode_spec[:2000]}"
                )

        # Extract page count
        n_pages = 10
        page_match = re.search(r"(\d+)\s*[页份张]", task.prompt or "")
        if page_match:
            extracted = int(page_match.group(1))
            if 3 <= extracted <= 30:
                n_pages = extracted

        system_parts.append(f"\nGenerate exactly {n_pages} slides.")

        # Load source context if available
        source_context = ""
        if task.source_file_ids:
            source_context = await self._load_source_context(task.source_file_ids)

        user_prompt = task.prompt or "Create a presentation"
        if source_context:
            user_prompt = f"{user_prompt}\n\n## Source Material\n{source_context[:8000]}"

        result = await llm.complete_json(
            system_prompt="\n".join(system_parts),
            user_prompt=user_prompt,
            temperature=0.3,
            max_tokens=3000,
        )

        slides = result.get("slides", [])
        # Ensure correct page count
        if len(slides) < n_pages:
            for i in range(len(slides), n_pages):
                slides.append(
                    {
                        "order": i + 1,
                        "title": f"补充内容 {i + 1}",
                        "description": "",
                        "slide_type": "body",
                    }
                )
        slides = slides[:n_pages]
        # Re-number
        for i, s in enumerate(slides):
            s["order"] = i + 1

        summary = result.get("summary", f"大纲：{n_pages} 页")
        tokens = max(500, n_pages * 200)
        return {"summary": summary, "slides": slides, "tokens": tokens}

    async def _stage_points_general(self, outline: dict, task: GenerationTask) -> dict[str, Any]:
        """LLM-powered points stage for general mode."""
        from src.services.generation.llm_client import LLMClient

        llm = await LLMClient.from_user_credential(self.session, str(task.owner_id))

        slides = outline.get("slides", [])

        # Load source context if available
        source_context = ""
        if task.source_file_ids:
            source_context = await self._load_source_context(task.source_file_ids)

        system_prompt = (
            "You are a presentation content writer. For each slide in the outline, "
            "generate detailed bullet points and speaker notes.\n"
            "Output a JSON object with: slides (array of {order, title, bullet_points: string[], notes: string}).\n"
            "Each slide should have 3-5 concise, assertion-style bullet points.\n"
            "Notes should be 2-3 sentences of speaking guidance."
        )

        user_parts = [
            f"## Outline\n```json\n{__import__('json').dumps(slides, ensure_ascii=False)}\n```"
        ]
        if source_context:
            user_parts.append(f"## Source Material\n{source_context[:8000]}")

        result = await llm.complete_json(
            system_prompt=system_prompt,
            user_prompt="\n\n".join(user_parts),
            temperature=0.3,
            max_tokens=4000,
        )

        enriched = result.get("slides", [])
        # Merge back with outline data
        outline_map = {s["order"]: s for s in slides}
        merged = []
        for es in enriched:
            order = es.get("order", 0)
            base = outline_map.get(order, {})
            merged.append(
                {
                    "order": order,
                    "title": es.get("title", base.get("title", "")),
                    "description": base.get("description", ""),
                    "slide_type": base.get("slide_type", "body"),
                    "bullet_points": es.get("bullet_points", []),
                    "notes": es.get("notes", ""),
                }
            )
        # Fill missing slides
        for s in slides:
            if not any(m["order"] == s["order"] for m in merged):
                merged.append(
                    {
                        **s,
                        "bullet_points": [s.get("title", "要点")],
                        "notes": "",
                    }
                )
        merged.sort(key=lambda x: x["order"])

        summary = f"要点提取：{len(merged)} 页"
        tokens = max(1000, len(merged) * 400)
        return {"summary": summary, "slides": merged, "tokens": tokens}

    async def _stage_svg_general(self, points: dict, task: GenerationTask) -> dict[str, Any]:
        """LLM-powered SVG stage for general mode. Generates one SVG per slide."""
        import xml.etree.ElementTree as ET

        from src.services.generation.llm_client import LLMClient
        from src.services.generation.reference_loader import ReferenceLoader

        llm = await LLMClient.from_user_credential(self.session, str(task.owner_id))
        refs = ReferenceLoader()

        # Build system prompt with shared standards
        shared_standards = refs.load_shared_standards()
        system_parts = [
            "You are an expert SVG designer for PowerPoint presentations.",
            "Generate clean, well-structured SVG markup for a single slide.",
            "Canvas: viewBox='0 0 1280 720' (16:9 aspect ratio).",
            "Output ONLY the SVG markup, no markdown fences, no explanation.",
            "",
            "## Critical Rules (from shared standards)",
            "Banned SVG features: mask, <style>, class, external CSS, <foreignObject>,",
            "<symbol>+<use>, textPath, @font-face, <animate*>, <script>, <iframe>.",
            "Text must use raw Unicode. Use XML entities for & < >.",
            "Group related elements with <g>.",
        ]
        if shared_standards:
            # Include first 3000 chars of shared standards
            system_parts.append(f"\n## Shared Standards (excerpt)\n{shared_standards[:3000]}")

        # Add visual style context
        if task.visual_style:
            style_spec = refs.load_visual_style(task.visual_style)
            if style_spec:
                system_parts.append(f"\n## Visual Style: {task.visual_style}\n{style_spec[:2000]}")

        slides = points.get("slides", [])
        svg_slides = []
        total_tokens = 0

        for slide in slides:
            order = slide.get("order", 1)
            title = slide.get("title", "")
            bullets = slide.get("bullet_points", [])
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

            svg_text = await llm.complete(
                system_prompt="\n".join(system_parts),
                user_prompt=user_prompt,
                temperature=0.4,
                max_tokens=4000,
            )

            # Clean up: strip markdown fences if present
            svg_text = svg_text.strip()
            if svg_text.startswith("```"):
                first_newline = svg_text.index("\n")
                svg_text = svg_text[first_newline + 1 :]
            if svg_text.endswith("```"):
                svg_text = svg_text[:-3].strip()

            # Validate XML
            try:
                ET.fromstring(svg_text)
            except ET.ParseError:
                # Try to fix common issues
                if not svg_text.startswith("<?xml"):
                    svg_text = '<?xml version="1.0" encoding="UTF-8"?>\n' + svg_text
                try:
                    ET.fromstring(svg_text)
                except ET.ParseError as e:
                    logger.warning("svg_validation_failed", order=order, error=str(e))
                    # Generate a fallback SVG
                    svg_text = self._fallback_svg(title, bullets, order)

            svg_slides.append({"order": order, "svg": svg_text, "title": title})
            total_tokens += max(1000, len(svg_text) // 4)  # rough token estimate

            # Emit progress per slide
            await self._emit_ws(
                task.id, "svg", "running", extra={"slide_progress": f"{order}/{len(slides)}"}
            )

        summary = f"SVG 渲染：{len(svg_slides)} 张幻灯片"
        return {"summary": summary, "slides": svg_slides, "tokens": total_tokens}

    def _fallback_svg(self, title: str, bullets: list[str], order: int) -> str:
        """Generate a simple fallback SVG when LLM output fails validation."""
        bullet_svg = ""
        for i, bp in enumerate(bullets[:5]):
            y = 160 + i * 50
            bullet_svg += f'<circle cx="100" cy="{y - 5}" r="4" fill="#4A90D9"/>\n'
            bullet_svg += f'<text x="120" y="{y}" font-family="Arial" font-size="18" fill="#333">{bp}</text>\n'
        return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" width="1280" height="720">
  <rect width="1280" height="720" fill="#FFFFFF"/>
  <rect x="0" y="0" width="1280" height="10" fill="#4A90D9"/>
  <text x="80" y="80" font-family="Arial" font-size="36" font-weight="bold" fill="#1A1A1A">{title}</text>
  <line x1="80" y1="95" x2="300" y2="95" stroke="#4A90D9" stroke-width="4"/>
  {bullet_svg}
  <text x="1180" y="700" font-family="Arial" font-size="14" fill="#999">{order}</text>
</svg>"""

    async def _load_source_context(self, source_file_ids: list[uuid.UUID]) -> str:
        """Load parsed content from source documents via ParseResult.structure_json."""
        from src.db.models import ParseResult, Sample

        result = await self.session.execute(
            select(ParseResult, Sample.file_name)
            .join(Sample, ParseResult.sample_id == Sample.id)
            .where(ParseResult.sample_id.in_(source_file_ids))
        )
        contents = []
        for pr, file_name in result.all():
            if not pr.structure_json:
                continue
            chunks = pr.structure_json.get("text_chunks", [])
            if not chunks:
                continue
            file_content = "\n\n".join(
                chunk.get("text", "") for chunk in chunks if chunk.get("text")
            )
            if file_content.strip():
                contents.append(f"## {file_name}\n\n{file_content}")
        return "\n\n---\n\n".join(contents)[:20000]

    async def _fail_task(self, task: GenerationTask, error: str) -> None:
        task.status = TaskStatus.failed
        task.finished_at = datetime.now(timezone.utc)
        task.error_message = error[:2000]
        await self.session.commit()
        await self._emit_ws(task.id, "failed", "failed", extra={"error": error})

    async def _emit_ws(
        self,
        task_id: uuid.UUID,
        stage_or_status: str,
        status_value: str,
        extra: dict | None = None,
    ) -> None:
        await publish_ws_event(
            f"task:{task_id}",
            {
                "type": "task.progress",
                "task_id": str(task_id),
                "stage": stage_or_status,
                "status": status_value,
                "ts": datetime.now(timezone.utc).isoformat(),
                **(extra or {}),
            },
        )
