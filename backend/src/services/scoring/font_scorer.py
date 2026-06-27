"""FontScorer (FR-028 / T113) — score font family consistency of generated PPT.

Extracts font-family declarations from SVG stage outputs and scores consistency:
fewer distinct font families = more consistent = higher score.
"""

from __future__ import annotations

import re
import uuid
from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.observability import get_logger
from src.db.models import TraceStage

logger = get_logger("scoring.font")

# Match font-family declarations in SVG/CSS
_FONT_FAMILY_RE = re.compile(
    r"font-family\s*:\s*([^;}\"]+)",
    re.IGNORECASE,
)
# Match quoted font names
_QUOTED_FONT_RE = re.compile(r"""['"]([^'"]+)['"]""")

# System / fallback fonts to ignore in analysis
_SYSTEM_FONTS = {
    "serif",
    "sans-serif",
    "monospace",
    "cursive",
    "fantasy",
    "system-ui",
    "ui-serif",
    "ui-sans-serif",
    "ui-monospace",
    "emoji",
    "math",
}


def _extract_fonts_from_svg(svg_text: str) -> list[str]:
    """Extract all font-family values from SVG markup."""
    fonts: list[str] = []
    for m in _FONT_FAMILY_RE.finditer(svg_text):
        raw = m.group(1).strip()
        # Handle comma-separated font stacks: "Arial, Helvetica, sans-serif"
        for part in raw.split(","):
            part = part.strip().strip("'\"").strip().lower()
            if part and part not in _SYSTEM_FONTS and len(part) > 1:
                fonts.append(part)
    return fonts


class FontScorer:
    """Score font family consistency (fewer distinct families = higher score)."""

    name = "font"

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def score(self, task_id: uuid.UUID) -> float:
        stages = (
            (
                await self.session.execute(
                    select(TraceStage).where(
                        TraceStage.task_id == task_id, TraceStage.stage_name == "svg"
                    )
                )
            )
            .scalars()
            .all()
        )

        all_fonts: list[str] = []
        for stage in stages:
            if stage.output_summary:
                all_fonts.extend(_extract_fonts_from_svg(stage.output_summary))

        if not all_fonts:
            return 0.7  # neutral default when no font data available

        unique_fonts = set(all_fonts)
        n_unique = len(unique_fonts)

        # Ideal: 1-2 font families (heading + body). 3+ is increasingly inconsistent.
        if n_unique == 1:
            score = 1.0
        elif n_unique == 2:
            score = 0.9
        elif n_unique == 3:
            score = 0.7
        elif n_unique == 4:
            score = 0.5
        else:
            score = max(0.2, 1.0 - (n_unique - 2) * 0.15)

        # Bonus: if one font dominates (≥70% of declarations), add 0.05
        cnt = Counter(all_fonts)
        top_ratio = max(cnt.values()) / sum(cnt.values())
        if top_ratio >= 0.7:
            score = min(1.0, score + 0.05)

        return round(max(0.0, min(1.0, score)), 3)
