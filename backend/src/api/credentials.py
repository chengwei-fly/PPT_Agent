"""Credentials API — manages AgentScope provider credentials per user.

Uses AgentScope's CredentialFactory for schema generation and validation.
Stores credentials in PostgreSQL via the Credential ORM model.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import NotFoundError
from src.core.observability import get_logger
from src.core.security import CurrentUser
from src.db.models import Credential
from src.db.session import get_db_session

router = APIRouter()
logger = get_logger("api.credentials")


# ── AgentScope integration ──────────────────────────────────────────


def _get_credential_factory():
    """Lazy import to avoid hard failure if AgentScope isn't installed."""
    try:
        from agentscope.credential import CredentialFactory

        return CredentialFactory
    except ImportError:
        return None


# ── Response models ─────────────────────────────────────────────────


class CredentialResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    provider_type: str
    name: str
    is_default: bool
    credential_data: dict = Field(description="Credential fields (api_key masked)")
    created_at: Any
    updated_at: Any


class CredentialSchemaResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_type: str
    schema: dict


class CreateCredentialRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_type: str = Field(description="AgentScope credential type, e.g. 'openai_credential'")
    name: str = Field(default="", max_length=128)
    credential_data: dict = Field(description="Credential fields matching the provider schema")
    is_default: bool = False


class UpdateCredentialRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    credential_data: dict | None = None
    is_default: bool | None = None


# ── Endpoints ───────────────────────────────────────────────────────


@router.get("/schemas", response_model=list[CredentialSchemaResponse])
async def list_credential_schemas(user: CurrentUser) -> list[CredentialSchemaResponse]:
    """Return JSON schemas for all supported credential providers.

    The frontend uses these schemas to dynamically render credential forms.
    """
    factory = _get_credential_factory()
    if factory is None:
        return []

    schemas = factory.list_schemas()
    result = []
    for schema in schemas:
        # Extract provider type from the schema's 'type' field default
        provider_type = ""
        props = schema.get("properties", {})
        if "type" in props:
            default = props["type"].get("default", "")
            provider_type = default.replace("_credential", "")
        result.append(
            CredentialSchemaResponse(
                provider_type=provider_type or schema.get("title", "unknown"),
                schema=schema,
            )
        )
    return result


@router.get("", response_model=list[CredentialResponse])
async def list_credentials(
    user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> list[CredentialResponse]:
    """List all credentials for the current user (API keys are masked)."""
    result = await session.execute(
        select(Credential)
        .where(Credential.owner_id == user.id)
        .order_by(Credential.created_at.desc())
    )
    credentials = result.scalars()
    return [_mask_credential(c) for c in credentials]


@router.post("", response_model=CredentialResponse, status_code=201)
async def create_credential(
    body: CreateCredentialRequest,
    user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> CredentialResponse:
    """Create a new credential after validating against AgentScope schema."""
    factory = _get_credential_factory()
    if factory is None:
        # Fallback: store without AgentScope validation
        validated_data = body.credential_data
    else:
        # Validate using AgentScope's CredentialFactory
        data = {**body.credential_data, "type": body.provider_type}
        try:
            credential_obj = factory.from_dict(data)
            validated_data = credential_obj.model_dump()
        except Exception as e:
            from fastapi import HTTPException

            raise HTTPException(422, f"Invalid credential data: {e}")

    # If marking as default, unset other defaults for this provider
    if body.is_default:
        await session.execute(
            update(Credential)
            .where(
                Credential.owner_id == user.id,
                Credential.provider_type == body.provider_type,
                Credential.is_default == True,  # noqa: E712
            )
            .values(is_default=False)
        )

    cred = Credential(
        owner_id=user.id,
        provider_type=body.provider_type,
        name=body.name,
        credential_data=validated_data,
        is_default=body.is_default,
    )
    session.add(cred)
    await session.flush()
    logger.info("credential_created", user=str(user.id), provider=body.provider_type)
    return _mask_credential(cred)


@router.put("/{credential_id}", response_model=CredentialResponse)
async def update_credential(
    credential_id: uuid.UUID,
    body: UpdateCredentialRequest,
    user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> CredentialResponse:
    """Update a credential's name, data, or default status."""
    cred = (
        await session.execute(
            select(Credential).where(
                Credential.id == credential_id,
                Credential.owner_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if not cred:
        raise NotFoundError("Credential", str(credential_id))

    if body.name is not None:
        cred.name = body.name
    if body.credential_data is not None:
        factory = _get_credential_factory()
        if factory is not None:
            data = {**body.credential_data, "type": cred.provider_type}
            try:
                credential_obj = factory.from_dict(data)
                cred.credential_data = credential_obj.model_dump()
            except Exception as e:
                from fastapi import HTTPException

                raise HTTPException(422, f"Invalid credential data: {e}")
        else:
            cred.credential_data = body.credential_data
    if body.is_default is not None:
        if body.is_default:
            await session.execute(
                update(Credential)
                .where(
                    Credential.owner_id == user.id,
                    Credential.provider_type == cred.provider_type,
                    Credential.is_default == True,  # noqa: E712
                    Credential.id != credential_id,
                )
                .values(is_default=False)
            )
        cred.is_default = body.is_default

    await session.flush()
    return _mask_credential(cred)


@router.delete("/{credential_id}", status_code=204)
async def delete_credential(
    credential_id: uuid.UUID,
    user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Delete a credential."""
    cred = (
        await session.execute(
            select(Credential).where(
                Credential.id == credential_id,
                Credential.owner_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if not cred:
        raise NotFoundError("Credential", str(credential_id))
    await session.delete(cred)
    await session.flush()


# ── Helpers ─────────────────────────────────────────────────────────


def _mask_credential(cred: Credential) -> CredentialResponse:
    """Mask sensitive fields (api_key) in credential data."""
    masked_data = {}
    for k, v in cred.credential_data.items():
        if "key" in k.lower() or "secret" in k.lower() or "token" in k.lower():
            if isinstance(v, str) and len(v) > 4:
                masked_data[k] = v[:3] + "***" + v[-3:]
            elif isinstance(v, dict) and "SecretStr" in str(type(v)):
                masked_data[k] = "***"
            else:
                masked_data[k] = "***"
        else:
            masked_data[k] = v
    return CredentialResponse(
        id=cred.id,
        provider_type=cred.provider_type,
        name=cred.name,
        is_default=cred.is_default,
        credential_data=masked_data,
        created_at=cred.created_at,
        updated_at=cred.updated_at,
    )
