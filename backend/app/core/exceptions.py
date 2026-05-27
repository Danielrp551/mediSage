"""
Domain exceptions + global handlers.

Services raise these; routers don't have to catch them. The handlers
convert each to the uniform error shape `{success, detail, code?, errors?}`.
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppException(Exception):
    """Root for all domain exceptions."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR

    def __init__(self, detail: str = "Internal error", *, code: str | None = None) -> None:
        self.detail = detail
        self.code = code


class NotFoundException(AppException):
    status_code = status.HTTP_404_NOT_FOUND


class AlreadyExistsException(AppException):
    status_code = status.HTTP_409_CONFLICT


class UnauthorizedException(AppException):
    status_code = status.HTTP_401_UNAUTHORIZED


class ForbiddenException(AppException):
    status_code = status.HTTP_403_FORBIDDEN


class BadRequestException(AppException):
    status_code = status.HTTP_400_BAD_REQUEST


# ── Handlers ───────────────────────────────────────

def _error_response(status_code: int, detail: str, code: str | None = None, errors: list | None = None) -> JSONResponse:
    body: dict = {"success": False, "detail": detail}
    if code is not None:
        body["code"] = code
    if errors is not None:
        body["errors"] = errors
    return JSONResponse(status_code=status_code, content=body)


async def _app_handler(request: Request, exc: AppException) -> JSONResponse:
    return _error_response(exc.status_code, exc.detail, code=exc.code)


async def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return _error_response(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Validation failed",
        errors=exc.errors(),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Wire up handlers in `main.py`."""
    app.add_exception_handler(AppException, _app_handler)
    app.add_exception_handler(RequestValidationError, _validation_handler)
