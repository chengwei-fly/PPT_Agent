"""RFC 7807 Problem JSON error handling per contracts/error-codes.yaml."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import ORJSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.core.observability import get_logger

logger = get_logger("errors")


# ─── Domain error class ──────────────────────────────────────────────
class PPTagentError(Exception):
    """Base class for all PPTagent business errors.

    Maps to a Problem JSON response with a stable code, status, and details.
    """

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)

    def to_problem(self, request_id: str) -> dict[str, Any]:
        return {
            "type": f"https://docs.pptagent.local/errors/{self.code}",
            "title": self.message,
            "status": self.status_code,
            "code": self.code,
            "instance": request_id,
            "details": self.details,
        }


# ─── Common error classes (FR-008 / FR-020) ─────────────────────────
class PIIHitError(PPTagentError):
    def __init__(self, hit_fields: list[str], **kwargs: Any) -> None:
        super().__init__(
            code="PPTAGENT.PII_HIT",
            message=f"PII detected in fields: {', '.join(hit_fields)}",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details={"hit_fields": hit_fields, **kwargs},
        )


class RateLimitError(PPTagentError):
    def __init__(self, retry_after: int = 60, **kwargs: Any) -> None:
        super().__init__(
            code="PPTAGENT.RATE_LIMITED",
            message="Rate limit exceeded",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details={"retry_after_seconds": retry_after, **kwargs},
        )


class NotFoundError(PPTagentError):
    def __init__(self, resource: str, resource_id: str, **kwargs: Any) -> None:
        super().__init__(
            code="PPTAGENT.NOT_FOUND",
            message=f"{resource} '{resource_id}' not found",
            status_code=status.HTTP_404_NOT_FOUND,
            details={"resource": resource, "resource_id": resource_id, **kwargs},
        )


class UnauthorizedError(PPTagentError):
    def __init__(self, reason: str = "Invalid credentials", **kwargs: Any) -> None:
        super().__init__(
            code="PPTAGENT.UNAUTHORIZED",
            message=reason,
            status_code=status.HTTP_401_UNAUTHORIZED,
            details=kwargs,
        )


class ForbiddenError(PPTagentError):
    def __init__(self, reason: str = "Insufficient scope", **kwargs: Any) -> None:
        super().__init__(
            code="PPTAGENT.FORBIDDEN",
            message=reason,
            status_code=status.HTTP_403_FORBIDDEN,
            details=kwargs,
        )


class IdempotencyMismatchError(PPTagentError):
    def __init__(self, key: str, **kwargs: Any) -> None:
        super().__init__(
            code="PPTAGENT.IDEMPOTENCY_MISMATCH",
            message="Idempotency-Key has been used with a different request body",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details={"idempotency_key": key, **kwargs},
        )


# ─── Handler registration ───────────────────────────────────────────
def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(PPTagentError)
    async def _pptagent_error_handler(request: Request, exc: PPTagentError) -> ORJSONResponse:
        request_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))
        logger.warning(
            "domain_error",
            code=exc.code,
            status=exc.status_code,
            details=exc.details,
            request_id=request_id,
        )
        return ORJSONResponse(
            content=exc.to_problem(request_id),
            status_code=exc.status_code,
            headers={"X-Request-Id": request_id},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error_handler(request: Request, exc: StarletteHTTPException) -> ORJSONResponse:
        request_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))
        return ORJSONResponse(
            content={
                "type": f"https://docs.pptagent.local/errors/HTTP_{exc.status_code}",
                "title": str(exc.detail),
                "status": exc.status_code,
                "code": f"HTTP_{exc.status_code}",
                "instance": request_id,
            },
            status_code=exc.status_code,
            headers={"X-Request-Id": request_id},
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> ORJSONResponse:
        request_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))
        return ORJSONResponse(
            content={
                "type": "https://docs.pptagent.local/errors/VALIDATION_ERROR",
                "title": "Request validation failed",
                "status": status.HTTP_422_UNPROCESSABLE_ENTITY,
                "code": "PPTAGENT.VALIDATION_ERROR",
                "instance": request_id,
                "details": {"errors": exc.errors()},
            },
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            headers={"X-Request-Id": request_id},
        )

    @app.exception_handler(Exception)
    async def _unhandled_error_handler(request: Request, exc: Exception) -> ORJSONResponse:
        request_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))
        logger.exception("unhandled_error", request_id=request_id, error=str(exc))
        return ORJSONResponse(
            content={
                "type": "https://docs.pptagent.local/errors/INTERNAL_ERROR",
                "title": "Internal server error",
                "status": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "code": "PPTAGENT.INTERNAL_ERROR",
                "instance": request_id,
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            headers={"X-Request-Id": request_id},
        )
