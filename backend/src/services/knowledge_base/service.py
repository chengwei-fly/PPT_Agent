"""Knowledge base service — parse → PII → embed (T061)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.observability import get_logger
from src.core.pii import get_pii_detector
from src.db.models import ParseResult, ParseStatus, Sample
from src.scheduler.queue import publish_ws_event
from src.services.knowledge_base.embedder import Embedder
from src.storage.minio import get_object
from src.tools.sample_parser import SampleParserTool

logger = get_logger("kb.service")

# PII detector singleton
_detector = get_pii_detector()


async def enqueue_parse(sample_id: str) -> None:
    """Enqueue a sample for async parsing via Redis Stream.

    Publishes to the 'parse_jobs' stream so the worker can pick it up.
    If Redis is unavailable, falls back to inline parse (MVP behavior).
    """
    try:
        from src.scheduler.queue import publish_event

        await publish_event(
            "parse_jobs",
            {
                "sample_id": sample_id,
                "enqueued_at": datetime.utcnow().isoformat(),
            },
        )
        logger.info("parse_enqueued", sample_id=sample_id)
    except Exception as e:
        # Fallback: trigger inline if Redis unavailable
        logger.warning("enqueue_fallback_inline", sample_id=sample_id, error=str(e))
        from src.db.session import async_session_factory

        async with async_session_factory() as session:
            await parse_and_index_sample(session, uuid.UUID(sample_id))


async def parse_and_index_sample(session: AsyncSession, sample_id: uuid.UUID) -> None:
    """End-to-end: parse → PII → embed → index. Idempotent."""
    sample = (
        await session.execute(select(Sample).where(Sample.id == sample_id))
    ).scalar_one_or_none()
    if not sample:
        logger.warning("parse_skip_not_found", sample_id=str(sample_id))
        return

    # Avoid re-parsing
    if sample.parse_status == ParseStatus.parsed:
        return

    sample.parse_status = ParseStatus.parsing
    await session.commit()

    try:
        # ── 1. Read raw bytes from MinIO ───────────────────────────
        bucket, key = _parse_minio_path(sample.raw_path)
        raw_bytes = get_object(bucket, key)

        # ── 2. Parse with version-pinned parser ────────────────────
        parser = SampleParserTool()
        parse_result_data = await parser.func(
            data=raw_bytes, file_type=sample.file_type.value, file_name=sample.file_name
        )

        # ── 3. PII scan on extracted text ───────────────────────────
        pii_fields = parse_result_data.get("text_chunks", [])
        pii_summary: dict[str, Any] = {"hit_count": 0, "fields": []}
        for chunk in pii_fields:
            if "text" in chunk:
                result = _detector.detect(chunk["text"])
                if result.has_pii:
                    chunk["text"] = result.redacted_text
                    pii_summary["hit_count"] += len(result.hits)
                    pii_summary["fields"] = sorted(
                        set(pii_summary["fields"]) | {h.field for h in result.hits}
                    )

        # ── 4. Persist ParseResult ─────────────────────────────────
        existing = (
            await session.execute(select(ParseResult).where(ParseResult.sample_id == sample.id))
        ).scalar_one_or_none()
        if existing:
            existing.structure_json = parse_result_data
            existing.parse_version = parse_result_data.get("parse_version", "1.0.0")
            existing.parse_finished_at = datetime.utcnow()
            existing.error_message = None
        else:
            pr = ParseResult(
                sample_id=sample.id,
                structure_json=parse_result_data,
                parse_version=parse_result_data.get("parse_version", "1.0.0"),
                parse_finished_at=datetime.utcnow(),
            )
            session.add(pr)

        # ── 5. Embed chunks async ─────────────────────────────────
        embedder = Embedder()
        await embedder.embed_sample_chunks(session, sample, pii_fields)

        # ── 6. Mark sample parsed ─────────────────────────────────
        sample.parse_status = ParseStatus.parsed
        sample.parsed_at = datetime.utcnow()
        sample.parse_page_count = parse_result_data.get("page_count", 0)
        sample.pii_summary = pii_summary
        await session.commit()

        await publish_ws_event(
            f"sample:{sample.id}",
            {
                "type": "sample.parsed",
                "sample_id": str(sample.id),
                "page_count": sample.parse_page_count,
            },
        )
        logger.info(
            "sample_parsed",
            sample_id=str(sample.id),
            page_count=sample.parse_page_count,
            pii_hits=pii_summary["hit_count"],
        )
    except Exception as e:
        sample.parse_status = ParseStatus.failed
        # Try to record error in ParseResult
        existing = (
            await session.execute(select(ParseResult).where(ParseResult.sample_id == sample.id))
        ).scalar_one_or_none()
        if existing:
            existing.error_message = str(e)[:2000]
        await session.commit()
        logger.exception("parse_failed", sample_id=str(sample.id), error=str(e))


def _parse_minio_path(path: str) -> tuple[str, str]:
    """Parse 's3://bucket/key' → (bucket, key)."""
    if path.startswith("s3://"):
        rest = path[5:]
        bucket, _, key = rest.partition("/")
        return bucket, key
    return "ppt-hot", path
