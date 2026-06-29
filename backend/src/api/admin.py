"""Admin API — curated material library operations (T900 / US6 extension).

Endpoints:

* ``POST /admin/material-library/import``     — upload a single PPTX and ingest
* ``POST /admin/material-library/import-dir`` — point at a server-side path
* ``GET  /admin/material-library/stats``     — counts of curated assets
* ``POST /admin/material-library/reset``      — DESTRUCTIVE: clear all curated assets
* ``POST /admin/material-library/reembed``    — recompute embeddings only

All endpoints require the ``X-Admin-Token`` header (matches
``settings.dev_api_key`` until a real RBAC story is in place). In dev
mode the ``dev-key`` token is sufficient.
"""

from __future__ import annotations

import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.observability import get_logger
from src.db.models import SlideAsset
from src.db.session import get_db_session
from src.services.material_importer.importer import (
    CuratedImporter,
    drop_curated_assets,
)

logger = get_logger("api.admin")
router = APIRouter(prefix="/admin/material-library", tags=["admin"])


# ─── Auth gate ────────────────────────────────────────────────────


def _require_admin(x_admin_token: Annotated[str | None, Header()] = None) -> None:
    expected = (settings.dev_api_key or "").strip()
    if not expected:
        # No token configured — refuse by default. Operators can override
        # with a real RBAC layer when one is introduced.
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "admin disabled")
    if not x_admin_token or x_admin_token != expected:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin token required")


# ─── Schemas ──────────────────────────────────────────────────────


class ImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    use_llm: bool = Field(False, description="Prefer multimodal LLM if available")
    llm_model: str | None = Field(None, description="Override multimodal model")
    max_assets: int | None = Field(None, ge=1, le=10000)
    dry_run: bool = Field(False, description="Extract + classify but do not persist")


class ImportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    files_seen: int
    files_failed: int
    assets_extracted: int
    assets_inserted: int
    assets_updated: int
    assets_skipped: int
    inserted_ids: list[str]
    failures: list[str]
    classification_counts: dict[str, int]


class CuratedStats(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int
    by_visual_type: dict[str, int]
    by_source_file: dict[str, int]
    last_import_at: str | None


# ─── Endpoints ────────────────────────────────────────────────────


@router.post(
    "/import",
    response_model=ImportResponse,
    status_code=status.HTTP_200_OK,
)
async def import_uploaded_file(
    file: Annotated[UploadFile, File(description="PPTX/PPT file to ingest")],
    use_llm: bool = False,
    llm_model: str | None = None,
    max_assets: int | None = None,
    dry_run: bool = False,
    _: None = Depends(_require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> ImportResponse:
    """Ingest a single uploaded PPTX. Saves to a temp dir then imports."""
    if not file.filename:
        raise HTTPException(400, "missing filename")
    suffix = Path(file.filename).suffix.lower()
    if suffix not in {".pptx", ".ppt"}:
        raise HTTPException(415, f"unsupported file type: {suffix}")

    tmpdir = Path(tempfile.mkdtemp(prefix="curated_import_"))
    try:
        target = tmpdir / file.filename
        with target.open("wb") as fh:
            shutil.copyfileobj(file.file, fh)
        importer = CuratedImporter(
            session,
            use_llm=use_llm,
            llm_model=llm_model,
        )
        report = await importer.import_directory(
            tmpdir, dry_run=dry_run, max_assets=max_assets
        )
        if not dry_run:
            await session.commit()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return _report_to_response(report)


@router.post(
    "/import-dir",
    response_model=ImportResponse,
    status_code=status.HTTP_200_OK,
)
async def import_server_dir(
    payload: ImportRequest,
    path: str = "",
    _: None = Depends(_require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> ImportResponse:
    """Ingest every PPTX in a server-side directory."""
    if not path:
        raise HTTPException(400, "path is required")
    target = Path(path)
    if not target.exists() or not target.is_dir():
        raise HTTPException(404, f"directory not found: {path}")
    if not settings.curated_library_enabled:
        raise HTTPException(503, "curated library is disabled in settings")
    importer = CuratedImporter(
        session,
        use_llm=payload.use_llm,
        llm_model=payload.llm_model,
    )
    max_assets = payload.max_assets
    if settings.curated_library_max_assets_per_run > 0:
        if max_assets is None or max_assets > settings.curated_library_max_assets_per_run:
            max_assets = settings.curated_library_max_assets_per_run
    report = await importer.import_directory(
        target, dry_run=payload.dry_run, max_assets=max_assets
    )
    if not payload.dry_run:
        await session.commit()
    return _report_to_response(report)


@router.get("/stats", response_model=CuratedStats)
async def get_stats(
    _: None = Depends(_require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> CuratedStats:
    """Return aggregate counts of curated assets."""
    total = (
        await session.execute(
            select(func.count(SlideAsset.id)).where(
                SlideAsset.source_sample_id.is_(None),
                SlideAsset.metadata_json["curated"].astext == "true",
                SlideAsset.deleted_at.is_(None),
            )
        )
    ).scalar_one() or 0

    by_vt_rows = (
        await session.execute(
            select(SlideAsset.visual_type, func.count(SlideAsset.id))
            .where(
                SlideAsset.source_sample_id.is_(None),
                SlideAsset.metadata_json["curated"].astext == "true",
                SlideAsset.deleted_at.is_(None),
            )
            .group_by(SlideAsset.visual_type)
        )
    ).all()
    by_visual_type = {str(vt): int(c) for vt, c in by_vt_rows}

    by_src_rows = (
        await session.execute(
            select(
                SlideAsset.metadata_json["source_file"].astext.label("src"),
                func.count(SlideAsset.id),
            )
            .where(
                SlideAsset.source_sample_id.is_(None),
                SlideAsset.metadata_json["curated"].astext == "true",
                SlideAsset.deleted_at.is_(None),
            )
            .group_by("src")
        )
    ).all()
    by_source_file = {str(s) if s else "unknown": int(c) for s, c in by_src_rows}

    last_import = (
        await session.execute(
            select(func.max(SlideAsset.indexed_at)).where(
                SlideAsset.source_sample_id.is_(None),
                SlideAsset.metadata_json["curated"].astext == "true",
            )
        )
    ).scalar()

    return CuratedStats(
        total=int(total),
        by_visual_type=by_visual_type,
        by_source_file=by_source_file,
        last_import_at=last_import.isoformat() if last_import else None,
    )


@router.post("/reset", status_code=status.HTTP_200_OK)
async def reset_library(
    _: None = Depends(_require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """DESTRUCTIVE: hard-delete all curated assets."""
    deleted = await drop_curated_assets(session)
    await session.commit()
    logger.warning("curated_library_reset", deleted=deleted)
    return {"deleted": deleted}


@router.post("/reembed", status_code=status.HTTP_200_OK)
async def reembed_all(
    _: None = Depends(_require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Recompute embeddings for every curated asset."""
    from src.services.parsing.embed_writer import ensure_embedding_for_asset

    rows = (
        await session.execute(
            select(SlideAsset).where(
                SlideAsset.source_sample_id.is_(None),
                SlideAsset.metadata_json["curated"].astext == "true",
                SlideAsset.deleted_at.is_(None),
            )
        )
    ).scalars()
    n = 0
    for asset in rows:
        await ensure_embedding_for_asset(session, asset)
        n += 1
    await session.commit()
    return {"reembedded": n}


# ─── helpers ──────────────────────────────────────────────────────


def _report_to_response(report) -> ImportResponse:
    return ImportResponse(
        files_seen=report.files_seen,
        files_failed=report.files_failed,
        assets_extracted=report.assets_extracted,
        assets_inserted=report.assets_inserted,
        assets_updated=report.assets_updated,
        assets_skipped=report.assets_skipped,
        inserted_ids=report.inserted_ids,
        failures=report.failures,
        classification_counts=report.classification_counts,
    )
