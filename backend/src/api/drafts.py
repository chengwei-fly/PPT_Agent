"""Drafts API — /drafts (US6 / T234-T235, T252)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import (
    NotFoundError,
    PPTagentError,
)
from src.core.observability import get_logger
from src.core.security import CurrentUser
from src.db.models import Draft, DraftSlide, DraftSlideSourceType
from src.db.session import get_db_session
from src.scheduler.queue import publish_ws_event
from src.services.draft.draft_service import DraftService
from src.services.draft.lock import acquire_lock, release_lock

logger = get_logger("api.drafts")
router = APIRouter(prefix="/drafts")


# ─── DTOs ──────────────────────────────────────────────────────────
class CreateDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(..., min_length=1, max_length=255)
    base_style: dict | None = None


class UpdateDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = None
    last_saved_revision: int = Field(..., description="Optimistic concurrency token")
    base_style: dict | None = None


class UpdateDraftSlideRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = None
    body_text: str | None = None
    notes: str | None = None
    materialized_svg: str | None = None


class DraftSlideResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    draft_id: uuid.UUID
    slide_order: int
    source_type: DraftSlideSourceType
    material_id: uuid.UUID | None
    generated_stage_id: uuid.UUID | None
    title: str | None
    body_text: str | None
    notes: str | None


class DraftResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    owner_id: uuid.UUID
    title: str
    status: str
    last_saved_revision: int
    editor_user_id: uuid.UUID | None
    lock_acquired_at: datetime | None
    lock_expires_at: datetime | None
    created_at: datetime
    updated_at: datetime


class InsertSlideRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    material_id: uuid.UUID | None = None
    generated_stage_id: uuid.UUID | None = None
    insert_at: int | None = Field(None, description="0-based insert position; append if None")


# ─── Routes ────────────────────────────────────────────────────────
@router.get("", response_model=list[DraftResponse])
async def list_drafts(
    user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
    limit: int = 50,
) -> list[Draft]:
    return await DraftService(session).list_for_user(user_id=user.id, limit=limit)


@router.post("", response_model=DraftResponse, status_code=status.HTTP_201_CREATED)
async def create_draft(
    body: CreateDraftRequest,
    user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> Draft:
    draft = await DraftService(session).create(
        owner_id=user.id, title=body.title, base_style=body.base_style
    )
    await session.commit()
    return draft


@router.get("/{draft_id}", response_model=DraftResponse)
async def get_draft(
    draft_id: uuid.UUID,
    user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> Draft:
    draft = await DraftService(session).get(draft_id=draft_id, owner_id=user.id)
    if not draft:
        raise NotFoundError("Draft", str(draft_id))
    return draft


@router.patch("/{draft_id}", response_model=DraftResponse)
async def update_draft(
    draft_id: uuid.UUID,
    body: UpdateDraftRequest,
    user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> Draft:
    """Optimistic-locked update — returns 412 on revision mismatch."""
    try:
        draft = await DraftService(session).update(
            draft_id=draft_id,
            owner_id=user.id,
            revision=body.last_saved_revision,
            title=body.title,
            base_style=body.base_style,
        )
    except PPTagentError:
        raise
    except Exception as e:
        if "REVISION_MISMATCH" in str(e):
            raise PPTagentError(
                code="PPTAGENT.DRAFT_REVISION_MISMATCH",
                message="Draft was modified by another writer; reload and retry",
                status_code=412,
            )
        raise
    await session.commit()
    return draft


@router.delete("/{draft_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_draft(
    draft_id: uuid.UUID,
    user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> None:
    await DraftService(session).soft_delete(draft_id=draft_id, owner_id=user.id)
    await session.commit()


# ─── Lock management (US6 R10) ────────────────────────────────────
@router.post("/{draft_id}/lock", response_model=DraftResponse)
async def acquire_draft_lock(
    draft_id: uuid.UUID,
    user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> Draft:
    draft = await acquire_lock(
        session,
        draft_id=draft_id,
        owner_id=user.id,
        editor_user_id=user.id,
        ttl=timedelta(minutes=30),
    )
    await session.commit()
    await publish_ws_event(
        f"draft:{draft_id}",
        {
            "type": "draft.locked",
            "draft_id": str(draft_id),
            "editor_user_id": str(user.id),
        },
    )
    return draft


@router.delete("/{draft_id}/lock", status_code=status.HTTP_204_NO_CONTENT)
async def release_draft_lock(
    draft_id: uuid.UUID,
    user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> None:
    await release_lock(session, draft_id=draft_id, user_id=user.id)
    await session.commit()
    await publish_ws_event(
        f"draft:{draft_id}",
        {"type": "draft.unlocked", "draft_id": str(draft_id)},
    )


# ─── Slides ────────────────────────────────────────────────────────
@router.post(
    "/{draft_id}/slides",
    response_model=DraftSlideResponse,
    status_code=status.HTTP_201_CREATED,
)
async def insert_draft_slide(
    draft_id: uuid.UUID,
    body: InsertSlideRequest,
    user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> DraftSlide:
    slide = await DraftService(session).insert_slide(
        draft_id=draft_id,
        owner_id=user.id,
        material_id=body.material_id,
        generated_stage_id=body.generated_stage_id,
        insert_at=body.insert_at,
    )
    await session.commit()
    await publish_ws_event(
        f"draft:{draft_id}",
        {
            "type": "draft.slide.inserted",
            "draft_id": str(draft_id),
            "slide_id": str(slide.id),
            "slide_order": slide.slide_order,
            "source_type": slide.source_type.value,
        },
    )
    return slide


@router.patch(
    "/{draft_id}/slides/{slide_id}",
    response_model=DraftSlideResponse,
)
async def update_draft_slide(
    draft_id: uuid.UUID,
    slide_id: uuid.UUID,
    body: UpdateDraftSlideRequest,
    user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> DraftSlide:
    slide = await DraftService(session).update_slide(
        draft_id=draft_id,
        slide_id=slide_id,
        owner_id=user.id,
        **body.model_dump(exclude_none=True),
    )
    await session.commit()
    return slide


@router.delete(
    "/{draft_id}/slides/{slide_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_draft_slide(
    draft_id: uuid.UUID,
    slide_id: uuid.UUID,
    user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> None:
    await DraftService(session).delete_slide(draft_id=draft_id, slide_id=slide_id, owner_id=user.id)
    await session.commit()


# ─── Export ────────────────────────────────────────────────────────
@router.post("/{draft_id}/export", status_code=status.HTTP_202_ACCEPTED)
async def export_draft(
    draft_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Start async PPTX export with source attribution (FR-036, T252)."""
    from src.services.export.draft_exporter import DraftExporter

    job = await DraftExporter(session).create_job(draft_id=draft_id, owner_id=user.id)
    await session.commit()
    # run_export is a static method that creates its own session — safe for BackgroundTasks
    background_tasks.add_task(DraftExporter.run_export, str(job.id))
    return {
        "job_id": str(job.id),
        "status": "queued",
        "progress": 0,
        "poll_url": f"/api/v1/drafts/{draft_id}/export/{job.id}",
    }


@router.get("/{draft_id}/export/{job_id}")
async def get_export_status(
    draft_id: uuid.UUID,
    job_id: uuid.UUID,
    user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    from src.core.errors import NotFoundError
    from src.db.models import DraftExportJob

    job = (
        await session.execute(
            select(DraftExportJob).where(
                DraftExportJob.id == job_id, DraftExportJob.draft_id == draft_id
            )
        )
    ).scalar_one_or_none()
    if not job:
        raise NotFoundError("DraftExportJob", str(job_id))
    return {
        "job_id": str(job.id),
        "status": job.status,
        "progress": job.progress,
        "pptx_path": job.pptx_path,
        "error_message": job.error_message,
    }
