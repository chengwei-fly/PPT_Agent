"""Sample API — POST /samples/batch, GET /samples, DELETE /samples/{id} (T065-T067)."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import NotFoundError
from src.core.observability import get_logger
from src.core.pii import get_pii_detector
from src.core.security import CurrentUser
from src.db.models import FileType, ParseStatus, Sample
from src.db.session import get_db_session
from src.scheduler.queue import publish_ws_event
from src.services.knowledge_base.service import enqueue_parse

logger = get_logger("api.samples")
router = APIRouter(prefix="/samples")

MAX_FILE_BYTES = 50 * 1024 * 1024  # FR-006: 50MB
MAX_BATCH_COUNT = 20  # FR-006: 20 files per batch


class SampleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    file_name: str
    file_type: FileType
    parse_status: ParseStatus
    parse_page_count: int | None
    pii_summary: dict | None
    uploaded_at: datetime
    parsed_at: datetime | None


@router.post("/batch", response_model=list[SampleResponse], status_code=status.HTTP_201_CREATED)
async def upload_samples(
    files: Annotated[list[UploadFile], File(description="PPTX/PDF/DOCX files")],
    user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> list[Sample]:
    """Batch upload samples (FR-006 / FR-007 / FR-008)."""
    if not files:
        raise HTTPException(400, "No files provided")
    if len(files) > MAX_BATCH_COUNT:
        raise HTTPException(400, f"Batch exceeds limit of {MAX_BATCH_COUNT} files")

    created: list[Sample] = []
    detector = get_pii_detector()

    for f in files:
        data = await f.read()
        if len(data) > MAX_FILE_BYTES:
            raise HTTPException(413, f"File '{f.filename}' exceeds 50MB")

        # Detect file type by extension
        ext = (f.filename or "").lower().split(".")[-1]
        try:
            file_type = FileType(ext)
        except ValueError:
            raise HTTPException(400, f"Unsupported file type: {ext}")

        # SHA-256 dedup (FR-010)
        file_hash = hashlib.sha256(data).hexdigest()
        existing = await session.execute(
            select(Sample).where(
                Sample.owner_id == user.id,
                Sample.file_hash == file_hash,
                Sample.deleted_at.is_(None),
            )
        )
        if existing.scalar_one_or_none():
            logger.info("sample_dedup_hit", filename=f.filename, hash=file_hash[:12])
            continue

        # PII pre-scan on filename
        pii = detector.detect(f.filename or "")

        # Store raw bytes to MinIO
        from src.storage.minio import put_object, raw_bucket

        key = f"samples/{user.id}/{file_hash[:2]}/{file_hash}.{ext}"
        put_object(
            bucket=raw_bucket(),
            key=key,
            data=data,
            content_type=_content_type(file_type),
        )

        sample = Sample(
            owner_id=user.id,
            file_name=f.filename or f"upload.{ext}",
            file_hash=file_hash,
            file_type=file_type,
            raw_path=key,
            parse_status=ParseStatus.pending,
            pii_summary=pii.to_summary() if pii.has_pii else None,
        )
        session.add(sample)
        await session.flush()
        created.append(sample)
        # Enqueue parse
        await enqueue_parse(str(sample.id))

    await session.commit()
    for s in created:
        await publish_ws_event(
            f"user:{user.id}:samples",
            {"type": "sample.uploaded", "sample_id": str(s.id), "filename": s.file_name},
        )
    logger.info("samples_uploaded", count=len(created), user_id=str(user.id))
    return created


@router.get("", response_model=list[SampleResponse])
async def list_samples(
    user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
    limit: int = 50,
    offset: int = 0,
) -> list[Sample]:
    """List user's samples (FR-007)."""
    result = await session.execute(
        select(Sample)
        .where(Sample.owner_id == user.id, Sample.deleted_at.is_(None))
        .order_by(Sample.uploaded_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars())


@router.delete("/{sample_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sample(
    sample_id: uuid.UUID,
    user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Soft-delete a sample (FR-007/FR-009). Cascade soft-deletes ParseResult + Embedding."""
    result = await session.execute(
        select(Sample).where(
            Sample.id == sample_id, Sample.owner_id == user.id, Sample.deleted_at.is_(None)
        )
    )
    sample = result.scalar_one_or_none()
    if not sample:
        raise NotFoundError("Sample", str(sample_id))

    sample.deleted_at = datetime.utcnow()
    await session.commit()
    await publish_ws_event(
        f"user:{user.id}:samples",
        {"type": "sample.deleted", "sample_id": str(sample_id)},
    )


def _content_type(file_type: FileType) -> str:
    return {
        FileType.pptx: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        FileType.pdf: "application/pdf",
        FileType.docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }.get(file_type, "application/octet-stream")
