"""Knowledge retriever tool (T063) — dual-mode (vector + keyword)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

# cosine_distance is a PostgreSQL function, not a Python import
# Use func.cosine_distance() from sqlalchemy instead
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.observability import get_logger
from src.db.models import Embedding, Sample
from src.services.knowledge_base.embedder import Embedder

logger = get_logger("kb.retriever")

# Vector weight vs keyword weight in the final score
VECTOR_WEIGHT = 0.6
KEYWORD_WEIGHT = 0.4


@dataclass
class RetrievalHit:
    sample_id: uuid.UUID
    chunk_index: int
    text: str
    score: float


class KnowledgeRetriever:
    """Hybrid retriever: cosine on embedding + trigram keyword match.

    R9: returns ranked list with combined score in [0, 1].
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.embedder = Embedder()

    async def retrieve(
        self,
        owner_id: uuid.UUID,
        query: str,
        top_k: int = 5,
    ) -> list[RetrievalHit]:
        """Return top-k chunks ranked by combined vector + keyword score."""
        if not query.strip():
            return []
        # ── Vector search (pgvector cosine) ───────────────────────
        query_vec = await self.embedder.embed_query(query)
        vector_q = (
            select(
                Embedding.sample_id,
                Embedding.chunk_index,
                Embedding.chunk_text,
                func.cosine_distance(Embedding.vector, query_vec).label("distance"),
            )
            .join(Sample, Sample.id == Embedding.sample_id)
            .where(Sample.owner_id == owner_id, Sample.deleted_at.is_(None))
            .order_by("distance")
            .limit(top_k * 3)  # over-fetch for keyword re-rank
        )
        vector_rows = (await self.session.execute(vector_q)).all()

        # ── Keyword search (PG trigram) ──────────────────────────
        kw_q = text("""
            SELECT sample_id, chunk_index, chunk_text,
                   similarity(chunk_text, :q) AS kw_score
            FROM embeddings
            JOIN samples ON samples.id = embeddings.sample_id
            WHERE samples.owner_id = :owner_id
              AND samples.deleted_at IS NULL
              AND chunk_text % :q
            ORDER BY kw_score DESC
            LIMIT :topk
        """)
        kw_rows = (
            (
                await self.session.execute(
                    kw_q, {"q": query, "owner_id": str(owner_id), "topk": top_k * 3}
                )
            ).all()
            if query
            else []
        )

        # ── Combine scores ───────────────────────────────────────
        combined: dict[tuple[uuid.UUID, int], RetrievalHit] = {}
        for sid, idx, txt, dist in vector_rows:
            vec_score = max(0.0, 1.0 - float(dist))
            key = (sid, idx)
            combined[key] = RetrievalHit(
                sample_id=sid,
                chunk_index=idx,
                text=txt,
                score=vec_score * VECTOR_WEIGHT,
            )
        for sid, idx, txt, kw in kw_rows:
            kw_score = float(kw)
            key = (sid, idx)
            if key in combined:
                combined[key].score += kw_score * KEYWORD_WEIGHT
            else:
                combined[key] = RetrievalHit(
                    sample_id=sid, chunk_index=idx, text=txt, score=kw_score * KEYWORD_WEIGHT
                )
        ranked = sorted(combined.values(), key=lambda h: -h.score)[:top_k]
        return ranked
