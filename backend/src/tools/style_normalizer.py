"""Style normalizer tool (US6 R13 / T240) — palette/font/layout harmonization."""

from __future__ import annotations

from typing import Any

from src.core.observability import get_logger
from src.db.models import SlideAsset

logger = get_logger("style_normalizer")


class StyleNormalizer:
    """Harmonize an asset's style to match a draft's overall_style.

    R13: Failure → preserve original + emit `normalized_failed=true` audit event.
    """

    def should_normalize(self, asset: SlideAsset) -> bool:
        return bool(asset.color_palette) or bool(asset.font_family)

    async def normalize(
        self,
        asset: SlideAsset,
        user_default_style: dict | None,
    ) -> dict[str, Any]:
        """Return normalized style fields. NEVER raises — falls back on failure."""
        try:
            target = user_default_style or self._default_style()
            palette = self._harmonize_palette(asset.color_palette, target.get("palette"))
            font_family = target.get("font_family") or asset.font_family
            return {
                "palette": palette,
                "font_family": font_family,
                "layout": target.get("layout", "mixed"),
                "normalized_failed": False,
            }
        except Exception as e:
            logger.warning("style_normalize_failed", asset_id=str(asset.id), error=str(e))
            return {
                "palette": asset.color_palette or self._default_style()["palette"],
                "font_family": asset.font_family,
                "layout": asset.visual_type.value if asset.visual_type else "mixed",
                "normalized_failed": True,
            }

    async def normalize_or_fallback(
        self,
        asset: SlideAsset,
        user_default_style: dict | None,
    ) -> dict[str, Any]:
        """Same as `normalize` but always records an audit-friendly response."""
        return await self.normalize(asset, user_default_style)

    def _default_style(self) -> dict[str, Any]:
        return {
            "palette": ["#1f2937", "#3b82f6", "#f9fafb", "#fbbf24", "#10b981"],
            "font_family": "PingFang SC, Microsoft YaHei, sans-serif",
            "layout": "mixed",
        }

    def _harmonize_palette(
        self, asset_palette: list[str], target_palette: list[str] | None
    ) -> list[str]:
        """Merge the asset's dominant colors with the target's anchor colors."""
        if not target_palette:
            return asset_palette or self._default_style()["palette"]
        # Keep top 3 most-frequent asset colors (visual continuity) + 2 anchor colors
        merged = list(asset_palette)[:3] + list(target_palette)[:2]
        # De-duplicate, keep first occurrence
        seen: set[str] = set()
        out: list[str] = []
        for c in merged:
            c_norm = c.lower()
            if c_norm not in seen:
                seen.add(c_norm)
                out.append(c)
        return out[:5]
