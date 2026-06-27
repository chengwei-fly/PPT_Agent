"""MaterialSearchService (T220) — hybrid BM25 + 嵌入向量 + visual_type boost (R9)."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.observability import get_logger
from src.db.models import Sample, SlideAsset, SlideVisualType

logger = get_logger("search.material")

# R9 weights
W_VECTOR = 0.4
W_KEYWORD = 0.4
W_VISUAL_BOOST = 0.2


@dataclass
class MaterialSearchResult:
    items: list[SlideAsset]
    total: int
    duration_ms: int


class MaterialSearchService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def hybrid_search(
        self,
        owner_id: uuid.UUID,
        query: str | None = None,
        visual_types: list[SlideVisualType] | None = None,
        industry_tags: list[str] | None = None,
        source_sample_ids: list[uuid.UUID] | None = None,
        include_orphan: bool = False,
        limit: int = 20,
    ) -> MaterialSearchResult:
        start = time.perf_counter()
        # Base filter: only assets visible to this user
        # An asset is visible if (a) its source_sample is owned by user and not deleted,
        # OR (b) it's an orphan (include_orphan=True)
        visibility = []
        if include_orphan:
            visibility.append(SlideAsset.source_sample_id.is_(None))
        visibility.append(
            SlideAsset.source_sample_id.in_(
                select(Sample.id).where(Sample.owner_id == owner_id, Sample.deleted_at.is_(None))
            )
        )

        stmt = select(SlideAsset).where(
            SlideAsset.deleted_at.is_(None),
            or_(*visibility),
        )

        if visual_types:
            stmt = stmt.where(SlideAsset.visual_type.in_(visual_types))
        if industry_tags:
            stmt = stmt.where(SlideAsset.industry_tags.op("&&")(industry_tags))
        if source_sample_ids:
            stmt = stmt.where(SlideAsset.source_sample_id.in_(source_sample_ids))

        # ── Vector score (if query) ──────────────────────────────
        if query and query.strip():
            from src.services.knowledge_base.embedder import Embedder

            embedder = Embedder()
            qvec = await embedder.embed_query(query)
            stmt = (
                stmt.add_columns(func.cosine_distance(SlideAsset.embedding, qvec).label("distance"))
                .order_by("distance")
                .limit(limit)
            )
            rows = (await self.session.execute(stmt)).all()
            # Re-hydrate: rows are (asset, distance)
            items_with_score = [
                (asset, max(0.0, 1.0 - float(distance)) * W_VECTOR) for asset, distance in rows
            ]
        else:
            rows = list((await self.session.execute(stmt.limit(limit * 3))).scalars())
            items_with_score = [(asset, 0.5) for asset in rows]

        # ── Keyword score (PG trigram) ───────────────────────────
        if query and query.strip():
            kw_stmt = select(
                SlideAsset.id,
                func.similarity(
                    func.coalesce(SlideAsset.body_text, "")
                    + " "
                    + func.coalesce(SlideAsset.title, ""),
                    query,
                ).label("kw"),
            ).where(
                SlideAsset.deleted_at.is_(None),
                or_(*visibility),
                or_(
                    func.coalesce(SlideAsset.body_text, "").op("%")(query),
                    func.coalesce(SlideAsset.title, "").op("%")(query),
                ),
            )
            kw_rows = (await self.session.execute(kw_stmt)).all()
            kw_scores = {row[0]: float(row[1]) for row in kw_rows}
        else:
            kw_scores = {}

        # ── Visual type boost (R9): prefer user-targeted types ────
        type_boost = {vt.value: W_VISUAL_BOOST for vt in (visual_types or [])}

        # ── Combine & rank ───────────────────────────────────────
        combined: list[tuple[SlideAsset, float]] = []
        for asset, vec_score in items_with_score:
            kw = kw_scores.get(asset.id, 0.0)
            boost = type_boost.get(asset.visual_type.value, 0.0)
            final = vec_score * W_VECTOR + kw * W_KEYWORD + boost
            combined.append((asset, final))
        combined.sort(key=lambda t: -t[1])
        top = combined[:limit]
        duration_ms = int((time.perf_counter() - start) * 1000)
        return MaterialSearchResult(
            items=[a for a, _ in top],
            total=len(combined),
            duration_ms=duration_ms,
        )
