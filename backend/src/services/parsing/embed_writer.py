"""Embedding writer for slide_assets (T213)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import SlideAsset
from src.services.knowledge_base.embedder import Embedder

_embedder: Embedder | None = None


def _get_embedder() -> Embedder:
    """Lazy-initialize the embedder singleton."""
    global _embedder
    if _embedder is None:
        _embedder = Embedder()
    return _embedder


async def ensure_embedding_for_asset(session: AsyncSession, asset: SlideAsset) -> None:
    """Compute and persist the embedding for a slide asset (idempotent)."""
    text = (asset.title or "") + " " + (asset.body_text or "")
    if not text.strip():
        return
    embedder = _get_embedder()
    vec = await embedder.embed_text(text)
    # Cast to list for JSONB storage fallback (use pgvector column in prod)
    asset.embedding = vec  # type: ignore[assignment]
    await session.flush()
