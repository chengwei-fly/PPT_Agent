"""SlideExtractor (T210) — per-page extraction with visual type classification."""

from __future__ import annotations

import re
from typing import Any

from src.core.observability import get_logger
from src.db.models import Sample, SlideAsset, SlideVisualType

logger = get_logger("parsing.slide_extractor")


class SlideExtractor:
    """Extracts per-slide SVG/text/image from a parsed sample and writes SlideAsset rows."""

    def __init__(self) -> None:
        self._palette_regex = re.compile(r"#[0-9a-fA-F]{6}")
        self._font_regex = re.compile(r"font-family[:=]\s*[\"']?([\w\s,]+?)[\"';]")

    async def extract_for_sample(
        self, sample: Sample, parse_result: dict[str, Any]
    ) -> list[SlideAsset]:
        """Read parse_result and create one SlideAsset per page."""
        page_summaries = parse_result.get("page_summaries", [])
        text_chunks = parse_result.get("text_chunks", [])
        assets: list[SlideAsset] = []
        for idx, page in enumerate(page_summaries):
            layout = page.get("layout", "body")
            chunk = text_chunks[idx] if idx < len(text_chunks) else {}
            text = chunk.get("text", "") if isinstance(chunk, dict) else ""
            assets.append(
                SlideAsset(
                    source_sample_id=sample.id,
                    page_index=idx,
                    visual_type=_layout_to_visual_type(layout),
                    title=self._extract_title(text),
                    body_text=text[:4000],
                    color_palette=self._extract_palette(text),
                    font_family=self._extract_font(text),
                    industry_tags=[],
                    metadata_json={"layout": layout, "source": "slide_extractor"},
                )
            )
        return assets

    def _extract_title(self, text: str) -> str | None:
        if not text:
            return None
        return text.split(" | ")[0][:255] if " | " in text else text.split("\n")[0][:255]

    def _extract_palette(self, text: str) -> list[str]:
        return list(dict.fromkeys(self._palette_regex.findall(text)))[:5] or []

    def _extract_font(self, text: str) -> str | None:
        m = self._font_regex.search(text)
        return m.group(1).strip() if m else None


def _layout_to_visual_type(layout: str) -> SlideVisualType:
    mapping = {
        "cover": SlideVisualType.cover,
        "toc": SlideVisualType.toc,
        "architecture": SlideVisualType.architecture,
        "flowchart": SlideVisualType.flowchart,
        "data": SlideVisualType.data,
        "body": SlideVisualType.body,
        "closing": SlideVisualType.closing,
    }
    return mapping.get(layout, SlideVisualType.mixed)
