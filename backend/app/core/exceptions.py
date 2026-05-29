"""
Domain exceptions + global handlers.

Services raise these; routers don't have to catch them. The handlers
convert each to the uniform error shape `{success, detail, code?, errors?}`.
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppException(Exception):  # noqa: N818 — root of a domain exception hierarchy, subclasses carry the `Error`/`Exception` suffix semantics
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


class ConflictException(AppException):
    """409 for state conflicts that aren't uniqueness violations — e.g.
    deleting a parent that still has active children. Distinct from
    `AlreadyExistsException` so the intent reads clearly at the call site."""

    status_code = status.HTTP_409_CONFLICT


# ── Handlers ───────────────────────────────────────


def _error_response(
    status_code: int, detail: str, code: str | None = None, errors: list | None = None
) -> JSONResponse:
    body: dict = {"success": False, "detail": detail}
    if code is not None:
        body["code"] = code
    if errors is not None:
        body["errors"] = errors
    return JSONResponse(status_code=status_code, content=body)


async def _app_handler(request: Request, exc: AppException) -> JSONResponse:
    return _error_response(exc.status_code, exc.detail, code=exc.code)


async def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    # `exc.errors()` can carry a non-serializable `ctx` (e.g. the original
    # ValueError raised by a custom field_validator). `jsonable_encoder`
    # coerces those to strings so `JSONResponse` doesn't 500 on 422s.
    return _error_response(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Validation failed",
        errors=jsonable_encoder(exc.errors()),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Wire up handlers in `main.py`."""
    app.add_exception_handler(AppException, _app_handler)
    app.add_exception_handler(RequestValidationError, _validation_handler)
