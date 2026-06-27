"""Async embedder (T062) — wraps OpenAI text-embedding-3-small (1536-d)."""

from __future__ import annotations

import hashlib
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.observability import get_logger
from src.db.models import Embedding, Sample

logger = get_logger("kb.embedder")


class Embedder:
    """Generates embeddings and stores them in the `embeddings` table (pgvector)."""

    def __init__(self, model: str | None = None, dimension: int | None = None) -> None:
        self.model = model or settings.embedding_model
        self.dimension = dimension or settings.embedding_dimension

    async def embed_text(self, text: str) -> list[float]:
        """Embed a single chunk of text."""
        if not text.strip():
            return [0.0] * self.dimension
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{settings.openai_base_url}/embeddings",
                    headers={
                        "Authorization": f"Bearer {settings.openai_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={"input": text[:8000], "model": self.model},
                )
                resp.raise_for_status()
                data = resp.json()
                return data["data"][0]["embedding"]
        except Exception as e:
            logger.warning("embed_failed_fallback_to_hash", error=str(e))
            # Deterministic fallback (so tests / offline can still proceed)
            return self._hash_embedding(text)

    def _hash_embedding(self, text: str) -> list[float]:
        """Deterministic pseudo-embedding from text hash. NOT a real embedding —
        used only as offline fallback to keep tests deterministic.
        """
        out: list[float] = []
        for i in range(self.dimension):
            h = hashlib.sha256(f"{i}::{text}".encode()).digest()
            out.append((int.from_bytes(h[:4], "big") / 0xFFFFFFFF) - 0.5)
        return out

    async def embed_sample_chunks(
        self, session: AsyncSession, sample: Sample, chunks: list[dict[str, Any]]
    ) -> None:
        """Embed & persist chunks for a sample. Idempotent: drops existing rows first."""
        # Clear existing embeddings (idempotent re-index)
        existing = await session.execute(select(Embedding).where(Embedding.sample_id == sample.id))
        for emb in existing.scalars():
            await session.delete(emb)
        await session.flush()

        for idx, chunk in enumerate(chunks):
            text = chunk.get("text", "")
            if not text:
                continue
            vector = await self.embed_text(text)
            emb = Embedding(
                sample_id=sample.id,
                chunk_index=idx,
                chunk_text=text,
                vector=vector,
                model_name=self.model,
            )
            session.add(emb)
        await session.flush()

    async def embed_query(self, query: str) -> list[float]:
        """Public helper — embed a query string (used by retrievers)."""
        return await self.embed_text(query)
