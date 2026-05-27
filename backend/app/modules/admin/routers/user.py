from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from app.core.dependencies import CurrentAuth, DBSession, RequirePermission
from app.modules.admin.schemas.user import (
    PasswordChange,
    UserCreate,
    UserCreatedResponse,
    UserDetail,
    UserItem,
    UserUpdate,
)
from app.modules.admin.services import user as user_service
from app.shared.base_schemas import (
    MessageResponse,
    PaginatedResponse,
    QueryRequest,
    SingleResponse,
)

router = APIRouter(prefix="/users", tags=["admin · users"])


UserIdPath = Annotated[str, Path(min_length=1, description="User UUID")]


@router.get(
    "/{user_id}",
    response_model=SingleResponse[UserDetail],
    dependencies=[Depends(RequirePermission("USERS_VIEW"))],
)
async def get_user(user_id: UserIdPath, db: DBSession) -> SingleResponse[UserDetail]:
    return await user_service.get_by_id(db, user_id)


@router.post(
    "/list",
    response_model=PaginatedResponse[UserItem],
    dependencies=[Depends(RequirePermission("USERS_VIEW"))],
)
async def list_users(query: QueryRequest, db: DBSession) -> PaginatedResponse[UserItem]:
    return await user_service.list_paginated(db, query)


@router.post(
    "",
    response_model=UserCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RequirePermission("USERS_CREATE"))],
)
async def create_user(
    payload: UserCreate, db: DBSession, actor: CurrentAuth
) -> UserCreatedResponse:
    return await user_service.create(db, payload, actor_id=actor.id)


@router.put(
    "/{user_id}",
    response_model=SingleResponse[UserDetail],
    dependencies=[Depends(RequirePermission("USERS_UPDATE"))],
)
async def update_user(
    user_id: UserIdPath,
    payload: UserUpdate,
    db: DBSession,
    actor: CurrentAuth,
) -> SingleResponse[UserDetail]:
    return await user_service.update(db, user_id, payload, actor_id=actor.id)


@router.post("/me/change-password", response_model=MessageResponse)
async def change_my_password(
    payload: PasswordChange, db: DBSession, auth: CurrentAuth
) -> MessageResponse:
    await user_service.change_password(db, auth.user, payload)
    return MessageResponse(detail="Password updated")
