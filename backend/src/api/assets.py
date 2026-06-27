"""Material library API — /materials (US6 / T222)."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.ops import material_search_duration_seconds
from src.core.errors import NotFoundError
from src.core.observability import get_logger
from src.core.security import CurrentUser
from src.db.models import Sample, SlideAsset, SlideVisualType
from src.db.session import get_db_session
from src.services.search.material_search import MaterialSearchService

logger = get_logger("api.materials")
router = APIRouter(prefix="/materials")


class MaterialResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    source_sample_id: uuid.UUID | None
    page_index: int
    visual_type: SlideVisualType
    title: str | None
    body_text: str | None
    thumbnail_path: str | None
    color_palette: list[str]
    font_family: str | None
    industry_tags: list[str]
    indexed_at: datetime | None


class MaterialDetailResponse(MaterialResponse):
    """Single-asset response that includes SVG payload."""

    svg_payload: str | None = None


class MaterialSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str | None = Field(None, description="Free text query (BM25 + vector)")
    visual_types: list[SlideVisualType] = Field(default_factory=list)
    industry_tags: list[str] = Field(default_factory=list)
    source_sample_ids: list[uuid.UUID] = Field(default_factory=list)
    include_orphan: bool = Field(False, description="Include slides whose sample was deleted")
    limit: int = Field(20, ge=1, le=100)


class MaterialSearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[MaterialResponse]
    total: int
    duration_ms: int


@router.get("", response_model=MaterialSearchResponse)
async def search_materials(
    user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
    q: str | None = Query(None, description="Search query"),
    visual_types: list[SlideVisualType] = Query(default_factory=list),
    industry_tags: list[str] = Query(default_factory=list),
    include_orphan: bool = Query(False),
    limit: int = Query(20, ge=1, le=100),
) -> MaterialSearchResponse:
    """Hybrid material search (R9: BM25 + 嵌入向量 + 视觉类型 boost)."""
    with material_search_duration_seconds.time():
        svc = MaterialSearchService(session)
        result = await svc.hybrid_search(
            owner_id=user.id,
            query=q,
            visual_types=visual_types,
            industry_tags=industry_tags,
            include_orphan=include_orphan,
            limit=limit,
        )
    return MaterialSearchResponse(
        items=result.items,
        total=result.total,
        duration_ms=result.duration_ms,
    )


@router.get("/{asset_id}", response_model=MaterialDetailResponse)
async def get_material(
    asset_id: uuid.UUID,
    user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> SlideAsset:
    result = await session.execute(
        select(SlideAsset).where(
            SlideAsset.id == asset_id,
            (SlideAsset.source_sample_id.is_(None))
            | SlideAsset.source_sample_id.in_(
                select(Sample.id).where(Sample.owner_id == user.id, Sample.deleted_at.is_(None))
            ),
            SlideAsset.deleted_at.is_(None),
        )
    )
    asset = result.scalar_one_or_none()
    if not asset:
        raise NotFoundError("SlideAsset", str(asset_id))
    return asset


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_material(
    asset_id: uuid.UUID,
    user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Soft-delete a material asset (orphan if it was linked to a sample)."""
    asset = (
        await session.execute(
            select(SlideAsset).where(
                SlideAsset.id == asset_id,
                SlideAsset.source_sample_id.in_(
                    select(Sample.id).where(Sample.owner_id == user.id, Sample.deleted_at.is_(None))
                ),
            )
        )
    ).scalar_one_or_none()
    if not asset:
        raise NotFoundError("SlideAsset", str(asset_id))
    asset.deleted_at = datetime.utcnow()
    await session.commit()


@router.post(
    "/{asset_id}/insert",
    status_code=status.HTTP_200_OK,
    response_model=MaterialResponse,
)
async def insert_material(
    asset_id: uuid.UUID,
    user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> SlideAsset:
    """Style-normalize and pre-fetch a material for insertion into a draft (FR-034)."""
    from src.tools.style_normalizer import StyleNormalizer

    asset = (
        await session.execute(
            select(SlideAsset).where(
                SlideAsset.id == asset_id,
                SlideAsset.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not asset:
        raise NotFoundError("SlideAsset", str(asset_id))

    normalizer = StyleNormalizer()
    if normalizer.should_normalize(asset):
        normalized = await normalizer.normalize(asset, user_default_style=None)
        asset.color_palette = normalized["palette"]
        asset.font_family = normalized.get("font_family", asset.font_family)
        await session.commit()
    return asset
