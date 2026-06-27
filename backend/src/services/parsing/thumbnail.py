"""Thumbnail renderer (T212) — PPTX → PNG @ 300dpi."""

from __future__ import annotations

import uuid

from src.core.observability import get_logger
from src.storage.minio import put_object

logger = get_logger("parsing.thumbnail")

THUMB_WIDTH = 480
THUMB_DPI = 300


async def render_thumbnail_from_svg(svg: str, asset_id: uuid.UUID) -> str | None:
    """Render a 480×270 PNG from a slide SVG. Best-effort."""
    try:
        import cairosvg  # type: ignore[import-not-found]
    except ImportError:
        logger.warning("cairosvg_not_available — skipping thumbnail")
        return None
    try:
        png_bytes = cairosvg.svg2png(
            bytestring=svg.encode("utf-8"),
            output_width=THUMB_WIDTH,
            output_height=int(THUMB_WIDTH * 9 / 16),
        )
        key = f"thumbnails/{asset_id}.png"
        put_object(bucket="ppt-hot", key=key, data=png_bytes, content_type="image/png")
        return f"s3://ppt-hot/{key}"
    except Exception as e:
        logger.warning("thumbnail_render_failed", asset_id=str(asset_id), error=str(e))
        return None
