"""Parsing pipeline — wires SlideExtractor into the parse flow (T211)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.observability import get_logger
from src.db.models import Sample, SlideAsset
from src.services.parsing.embed_writer import ensure_embedding_for_asset
from src.services.parsing.slide_extractor import SlideExtractor

logger = get_logger("parsing.pipeline")


async def run_post_parse_pipeline(session: AsyncSession, sample: Sample, parse_result: dict) -> int:
    """Run SlideExtractor on a freshly parsed sample. Returns count of new assets.

    Idempotent: existing assets for this sample are dropped first.
    """
    extractor = SlideExtractor()
    assets = await extractor.extract_for_sample(sample, parse_result)

    # Wipe existing assets (idempotent re-extraction)
    existing = await session.execute(
        select(SlideAsset).where(SlideAsset.source_sample_id == sample.id)
    )
    for a in existing.scalars():
        await session.delete(a)
    await session.flush()

    for asset in assets:
        session.add(asset)
    await session.flush()

    # Compute embeddings
    for asset in assets:
        await ensure_embedding_for_asset(session, asset)

    from datetime import datetime

    from sqlalchemy import update

    await session.execute(
        update(SlideAsset)
        .where(SlideAsset.id.in_([a.id for a in assets]))
        .values(indexed_at=datetime.utcnow())
    )
    await session.commit()

    logger.info("slide_assets_indexed", sample_id=str(sample.id), count=len(assets))
    return len(assets)
