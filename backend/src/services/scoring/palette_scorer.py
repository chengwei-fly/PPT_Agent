"""PaletteScorer (FR-028 / T112) — score color palette harmony of generated PPT.

Extracts dominant colors from SVG stage outputs and measures palette coherence
using normalized entropy: lower entropy (fewer dominant colors) = more harmonious.
"""

from __future__ import annotations

import re
import uuid
from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.observability import get_logger
from src.db.models import TraceStage

logger = get_logger("scoring.palette")

# Regex to match hex colors in SVG (#RGB, #RRGGBB, #RRGGBBAA)
_HEX_RE = re.compile(r"#(?:[0-9a-fA-F]{3}){1,2}(?:[0-9a-fA-F]{2})?")
# Regex for rgb()/rgba() in SVG styles
_RGB_RE = re.compile(r"rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})")
# Named SVG colors (common subset)
_NAMED_COLORS = {
    "black": "#000000",
    "white": "#ffffff",
    "red": "#ff0000",
    "green": "#008000",
    "blue": "#0000ff",
    "yellow": "#ffff00",
    "cyan": "#00ffff",
    "magenta": "#ff00ff",
    "gray": "#808080",
    "grey": "#808080",
    "orange": "#ffa500",
    "purple": "#800080",
}

# Neutral background colors to exclude from palette analysis
_EXCLUDE_COLORS = {"#ffffff", "#000000", "#fff", "#000"}


def _normalize_hex(raw: str) -> str | None:
    """Normalize a hex color string to lowercase #rrggbb form."""
    h = raw.lower().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) >= 6:
        return f"#{h[:6]}"
    return None


def _extract_colors_from_svg(svg_text: str) -> list[str]:
    """Extract all meaningful color values from SVG markup."""
    colors: list[str] = []
    for m in _HEX_RE.finditer(svg_text):
        c = _normalize_hex(m.group())
        if c and c not in _EXCLUDE_COLORS:
            colors.append(c)
    for m in _RGB_RE.finditer(svg_text):
        r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
        c = f"#{r:02x}{g:02x}{b:02x}"
        if c not in _EXCLUDE_COLORS:
            colors.append(c)
    return colors


class PaletteScorer:
    """Score color palette harmony (low entropy of dominant colors = harmonious)."""

    name = "palette"

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

        all_colors: list[str] = []
        for stage in stages:
            # Parse colors from the SVG output stored in output_summary
            if stage.output_summary:
                all_colors.extend(_extract_colors_from_svg(stage.output_summary))

        if not all_colors:
            return 0.5  # neutral when no color data available

        cnt = Counter(all_colors)
        total = sum(cnt.values())
        # Normalized Shannon entropy (inverted: lower entropy = more harmonious = higher score)
        import math

        entropy = -sum((c / total) * math.log2(c / total) for c in cnt.values())
        max_entropy = math.log2(len(cnt)) if len(cnt) > 1 else 1.0
        # Invert: 0 entropy (monochrome) = 1.0 score, max entropy = 0.0 score
        harmony = 1.0 - (entropy / max_entropy) if max_entropy > 0 else 1.0
        # Bonus for having a clear dominant color (top color > 40% of usage)
        top_ratio = max(cnt.values()) / total
        if top_ratio > 0.4:
            harmony = min(1.0, harmony + 0.1)
        return round(max(0.0, min(1.0, harmony)), 3)
