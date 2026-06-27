"""Data lifecycle API — POST /data/export, POST /data/delete-all (T104-T105)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import PPTagentError
from src.core.observability import get_logger
from src.core.security import CurrentUser
from src.db.session import get_db_session
from src.services.data_lifecycle.delete import delete_all_user_data
from src.services.data_lifecycle.export import export_user_data

logger = get_logger("api.data_lifecycle")
router = APIRouter(prefix="/data")


class ExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm: bool = False


class ExportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: str
    status: str
    download_url: str | None = None
    message: str


class DeleteAllRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmation_phrase: str = Field(..., description='MUST be exactly "DELETE ALL MY DATA"')


@router.post("/export", response_model=ExportResponse, status_code=status.HTTP_202_ACCEPTED)
async def export_data(
    body: ExportRequest,
    user: CurrentUser,
) -> ExportResponse:
    """Package raw + parse + preferences into a ZIP (FR-018, SC-006)."""
    if not body.confirm:
        return ExportResponse(
            job_id="",
            status="pending_confirmation",
            message="Set confirm=true to start export",
        )
    job_id = await export_user_data(user_id=str(user.id))
    return ExportResponse(
        job_id=job_id,
        status="running",
        message="Export started; check back via /security/events for completion",
    )


@router.post("/delete-all", status_code=status.HTTP_202_ACCEPTED)
async def delete_all(
    body: DeleteAllRequest,
    user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Hard-delete all user data (FR-009 + FR-019, SC-005).

    Requires 二次确认: confirmation_phrase MUST equal "DELETE ALL MY DATA".
    """
    if body.confirmation_phrase != "DELETE ALL MY DATA":
        raise PPTagentError(
            code="PPTAGENT.DELETE_CONFIRM_REQUIRED",
            message='confirmation_phrase must be exactly "DELETE ALL MY DATA"',
            status_code=400,
        )
    job_id = await delete_all_user_data(user_id=str(user.id), session=session)
    return {
        "job_id": job_id,
        "status": "queued",
        "purge_deadline": (datetime.utcnow()).isoformat(),
        "message": "All data will be removed from production DB within 24h and backups within 7d",
    }
