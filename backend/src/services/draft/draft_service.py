"""DraftService (T230) — CRUD + optimistic lock + autosave + slide operations."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import NotFoundError, PPTagentError
from src.core.observability import get_logger
from src.db.models import (
    Draft,
    DraftSlide,
    DraftSlideSourceType,
    SlideAsset,
    TraceStage,
)
from src.services.draft.lock import (
    is_locked_by_other,
)

logger = get_logger("draft.service")


class DraftService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── CRUD ─────────────────────────────────────────────────────
    async def list_for_user(self, user_id: uuid.UUID, limit: int = 50) -> list[Draft]:
        result = await self.session.execute(
            select(Draft)
            .where(Draft.owner_id == user_id, Draft.deleted_at.is_(None))
            .order_by(Draft.updated_at.desc())
            .limit(limit)
        )
        return list(result.scalars())

    async def get(self, draft_id: uuid.UUID, owner_id: uuid.UUID) -> Draft | None:
        return (
            await self.session.execute(
                select(Draft).where(
                    Draft.id == draft_id, Draft.owner_id == owner_id, Draft.deleted_at.is_(None)
                )
            )
        ).scalar_one_or_none()

    async def create(
        self,
        owner_id: uuid.UUID,
        title: str,
        base_style: dict | None = None,
    ) -> Draft:
        draft = Draft(
            owner_id=owner_id,
            title=title,
            overall_style=base_style,
            last_saved_revision=0,
        )
        self.session.add(draft)
        await self.session.flush()
        return draft

    async def update(
        self,
        draft_id: uuid.UUID,
        owner_id: uuid.UUID,
        revision: int,
        title: str | None = None,
        base_style: dict | None = None,
    ) -> Draft:
        draft = await self.get(draft_id, owner_id)
        if not draft:
            raise NotFoundError("Draft", str(draft_id))
        if is_locked_by_other(draft, owner_id):
            raise PPTagentError(
                code="PPTAGENT.DRAFT_LOCKED",
                message="Draft is currently locked by another writer; open as read-only",
                status_code=423,
            )
        if draft.last_saved_revision != revision:
            raise PPTagentError(
                code="PPTAGENT.DRAFT_REVISION_MISMATCH",
                message=f"Expected revision {draft.last_saved_revision}, got {revision}. Reload and retry.",
                status_code=412,
            )
        if title is not None:
            draft.title = title
        if base_style is not None:
            draft.overall_style = base_style
        draft.last_saved_revision += 1
        await self.session.flush()
        return draft

    async def soft_delete(self, draft_id: uuid.UUID, owner_id: uuid.UUID) -> None:
        draft = await self.get(draft_id, owner_id)
        if not draft:
            raise NotFoundError("Draft", str(draft_id))
        draft.deleted_at = datetime.utcnow()
        await self.session.flush()

    # ── Slide operations ────────────────────────────────────────
    async def insert_slide(
        self,
        draft_id: uuid.UUID,
        owner_id: uuid.UUID,
        material_id: uuid.UUID | None = None,
        generated_stage_id: uuid.UUID | None = None,
        insert_at: int | None = None,
    ) -> DraftSlide:
        draft = await self.get(draft_id, owner_id)
        if not draft:
            raise NotFoundError("Draft", str(draft_id))
        if is_locked_by_other(draft, owner_id):
            raise PPTagentError(
                code="PPTAGENT.DRAFT_LOCKED",
                message="Draft is locked; cannot insert slides",
                status_code=423,
            )

        if not material_id and not generated_stage_id:
            # Manual empty slide
            source_type = DraftSlideSourceType.manual
        elif material_id:
            source_type = DraftSlideSourceType.reused
            asset = (
                await self.session.execute(select(SlideAsset).where(SlideAsset.id == material_id))
            ).scalar_one_or_none()
            if not asset:
                raise NotFoundError("SlideAsset", str(material_id))
        else:
            source_type = DraftSlideSourceType.generated
            stage = (
                await self.session.execute(
                    select(TraceStage).where(TraceStage.id == generated_stage_id)
                )
            ).scalar_one_or_none()
            if not stage:
                raise NotFoundError("TraceStage", str(generated_stage_id))

        # Determine next slide_order
        max_order = (
            await self.session.execute(
                select(DraftSlide.slide_order)
                .where(DraftSlide.draft_id == draft_id)
                .order_by(DraftSlide.slide_order.desc())
                .limit(1)
            )
        ).scalar()
        next_order = (max_order or -1) + 1 if insert_at is None else insert_at

        slide = DraftSlide(
            draft_id=draft_id,
            slide_order=next_order,
            source_type=source_type,
            material_id=material_id,
            generated_stage_id=generated_stage_id,
        )
        self.session.add(slide)
        await self.session.flush()
        draft.last_saved_revision += 1
        return slide

    async def update_slide(
        self,
        draft_id: uuid.UUID,
        slide_id: uuid.UUID,
        owner_id: uuid.UUID,
        **fields: Any,
    ) -> DraftSlide:
        slide = (
            await self.session.execute(
                select(DraftSlide)
                .join(Draft, Draft.id == DraftSlide.draft_id)
                .where(
                    DraftSlide.id == slide_id,
                    DraftSlide.draft_id == draft_id,
                    Draft.owner_id == owner_id,
                )
            )
        ).scalar_one_or_none()
        if not slide:
            raise NotFoundError("DraftSlide", str(slide_id))
        for k, v in fields.items():
            if v is not None:
                setattr(slide, k, v)
        await self.session.flush()
        return slide

    async def delete_slide(
        self, draft_id: uuid.UUID, slide_id: uuid.UUID, owner_id: uuid.UUID
    ) -> None:
        slide = (
            await self.session.execute(
                select(DraftSlide)
                .join(Draft, Draft.id == DraftSlide.draft_id)
                .where(
                    DraftSlide.id == slide_id,
                    DraftSlide.draft_id == draft_id,
                    Draft.owner_id == owner_id,
                )
            )
        ).scalar_one_or_none()
        if not slide:
            raise NotFoundError("DraftSlide", str(slide_id))
        await self.session.delete(slide)
        await self.session.flush()

    async def reorder_slides(
        self, draft_id: uuid.UUID, owner_id: uuid.UUID, slide_ids_in_order: list[uuid.UUID]
    ) -> list[DraftSlide]:
        slides = (
            await self.session.execute(
                select(DraftSlide)
                .join(Draft, Draft.id == DraftSlide.draft_id)
                .where(DraftSlide.draft_id == draft_id, Draft.owner_id == owner_id)
                .order_by(DraftSlide.slide_order.asc())
            )
        ).scalars()
        by_id = {s.id: s for s in slides}
        # Validate all provided IDs belong to this draft
        invalid_ids = set(slide_ids_in_order) - set(by_id.keys())
        if invalid_ids:
            from src.core.errors import ValidationError

            raise ValidationError(
                f"Slide IDs {invalid_ids} do not belong to draft {draft_id}",
                code="PPTAGENT.DRAFT_SLIDE_MISMATCH",
            )
        for new_order, sid in enumerate(slide_ids_in_order):
            by_id[sid].slide_order = new_order
        await self.session.flush()
        return sorted(by_id.values(), key=lambda s: s.slide_order)
