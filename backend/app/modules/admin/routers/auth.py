from __future__ import annotations

from fastapi import APIRouter, Request

from app.core.config import get_settings
from app.core.dependencies import CurrentAuth, DBSession
from app.core.rate_limit import limiter
from app.modules.admin.schemas.auth import (
    AuthenticatedUser,
    LoginRequest,
    LoginResponse,
    RefreshRequest,
)
from app.modules.admin.services import auth as auth_service
from app.shared.base_schemas import MessageResponse

settings = get_settings()

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
@limiter.limit(settings.LOGIN_RATE_LIMIT)
async def login(request: Request, payload: LoginRequest, db: DBSession) -> LoginResponse:
    return await auth_service.login(db, email=payload.email, password=payload.password)


@router.post("/refresh", response_model=LoginResponse)
@limiter.limit(settings.AUTH_BURST_RATE_LIMIT)
async def refresh(request: Request, payload: RefreshRequest, db: DBSession) -> LoginResponse:
    return await auth_service.refresh(db, refresh_token=payload.refresh_token)


@router.post("/logout", response_model=MessageResponse)
@limiter.limit(settings.AUTH_BURST_RATE_LIMIT)
async def logout(request: Request, payload: RefreshRequest, db: DBSession) -> MessageResponse:
    await auth_service.logout(db, refresh_token=payload.refresh_token)
    return MessageResponse(detail="Logged out")


@router.get("/me", response_model=AuthenticatedUser)
async def me(auth: CurrentAuth) -> AuthenticatedUser:
    # Use fresh DB-loaded relationships, not the token claims — an admin
    # may have changed roles/permissions since the token was issued.
    user = auth.user
    return AuthenticatedUser(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        first_name=user.first_name,
        last_name=user.last_name,
        second_last_name=user.second_last_name,
        active=user.active,
        roles=sorted(r.name for r in user.roles),
        permissions=user.effective_permission_codes(),
    )
