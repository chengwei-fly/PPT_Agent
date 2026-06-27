"""Preference extractor (T077) — LLM-based rule induction from source_chains.

Constitution §V: source_chains MUST contain the sample/manual_edit/preference_apply fragments
that led to a preference rule being created.
"""

from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.observability import get_logger
from src.db.models import GenerationTask, Preference, PreferenceScope, TraceStage

logger = get_logger("preference.extractor")

PREFERENCE_EXTRACT_THRESHOLD = 5  # FR-011: 5 similar modifications → 1 rule


class PreferenceExtractor:
    """Infer preference rules from repeated user modifications across trace stages."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def extract_for_user(self, user_id: uuid.UUID) -> list[Preference]:
        """Find repeated modifications in trace_stages and consolidate them into rules."""
        # Group stages by modification hint (e.g., "logo position = top-right")
        task_stages = (
            await self.session.execute(
                select(TraceStage)
                .join(GenerationTask, GenerationTask.id == TraceStage.task_id)
                .where(GenerationTask.owner_id == user_id)
                .order_by(TraceStage.started_at.asc())
            )
        ).scalars()
        groups: dict[str, list[TraceStage]] = defaultdict(list)
        for s in task_stages:
            key = self._normalize_modification(s.input_summary, s.output_summary)
            if key:
                groups[key].append(s)

        new_prefs: list[Preference] = []
        next_id = await self._next_pref_id()
        for key, stages in groups.items():
            if len(stages) < PREFERENCE_EXTRACT_THRESHOLD:
                continue
            pref = Preference(
                id=next_id,
                owner_id=user_id,
                source_chains={
                    "trace_stage_ids": [str(s.id) for s in stages[:10]],
                    "task_ids": list({str(s.task_id) for s in stages[:10]}),
                    "modification_pattern": key,
                    "first_seen": stages[0].started_at.isoformat()
                    if stages[0].started_at
                    else None,
                    "last_seen": stages[-1].started_at.isoformat()
                    if stages[-1].started_at
                    else None,
                },
                rule_text=key,
                applies_to=self._infer_scope(stages),
                apply_count=0,
                ignore_count=0,
            )
            self.session.add(pref)
            new_prefs.append(pref)
            next_id = _increment_pref_id(next_id)
        await self.session.commit()
        logger.info("preferences_extracted", user_id=str(user_id), count=len(new_prefs))
        return new_prefs

    def _normalize_modification(self, input_summary: str, output_summary: str) -> str | None:
        """Detect modification patterns from input/output summaries.

        Uses keyword-based heuristics to extract reusable modification patterns.
        Full impl: use LLM to semantically compare input vs output and extract
        the specific modification rule.
        """
        combined = (input_summary + " " + output_summary).lower()

        # Pattern 1: explicit key=value hints (e.g., "position=right", "color=#4A90D9")
        for token in combined.split():
            if "=" in token and len(token) > 3:
                return token.strip(",.;:!?")

        # Pattern 2: position-related modifications
        position_keywords = [
            "位置",
            "position",
            "居左",
            "居右",
            "居中",
            "上方",
            "下方",
            "左上",
            "右上",
            "左下",
            "右下",
        ]
        for kw in position_keywords:
            if kw in combined:
                return f"position:{kw}"

        # Pattern 3: color/style modifications
        color_keywords = ["颜色", "color", "配色", "背景色", "字体色", "主题色", "色调"]
        for kw in color_keywords:
            if kw in combined:
                return f"style:{kw}"

        # Pattern 4: font modifications
        font_keywords = ["字体", "font", "字号", "加粗", "斜体", "font-size", "font-family"]
        for kw in font_keywords:
            if kw in combined:
                return f"font:{kw}"

        # Pattern 5: layout modifications
        layout_keywords = ["布局", "layout", "版式", "排列", "对齐", "间距", "留白"]
        for kw in layout_keywords:
            if kw in combined:
                return f"layout:{kw}"

        # Pattern 6: content additions/removals
        content_keywords = ["添加", "删除", "移除", "替换", "增加", "去掉", "保留"]
        for kw in content_keywords:
            if kw in combined:
                return f"content:{kw}"

        return None

    def _infer_scope(self, stages: list[TraceStage]) -> PreferenceScope:
        """Infer preference scope from the stage names involved.

        Maps stage names to slide scopes:
        - outline stage → cover/toc scope
        - points stage → body scope
        - svg stage → visual scope (body)
        - pptx stage → all
        """
        if not stages:
            return PreferenceScope.all

        stage_names = {s.stage_name for s in stages}

        # If only outline was modified, likely affects cover/toc
        if stage_names == {"outline"}:
            return PreferenceScope.cover
        # If only points were modified, likely affects body content
        if stage_names == {"points"}:
            return PreferenceScope.body
        # If svg was modified, affects visual layout
        if "svg" in stage_names:
            return PreferenceScope.body

        return PreferenceScope.all

    async def _next_pref_id(self) -> str:
        from sqlalchemy import func

        result = await self.session.execute(
            select(func.count(Preference.id)).where(Preference.id.like("P-%"))
        )
        count = (result.scalar() or 0) + 1
        return f"P-{count:03d}"


def _increment_pref_id(current: str) -> str:
    try:
        n = int(current.split("-")[1])
        return f"P-{n + 1:03d}"
    except (IndexError, ValueError):
        return current
