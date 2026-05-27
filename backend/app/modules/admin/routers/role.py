from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from app.core.dependencies import CurrentAuth, DBSession, RequirePermission
from app.modules.admin.schemas.role import (
    RoleCreate,
    RoleDetail,
    RoleItem,
    RoleOption,
    RoleUpdate,
)
from app.modules.admin.services import role as role_service
from app.shared.base_schemas import PaginatedResponse, QueryRequest, SingleResponse

router = APIRouter(prefix="/roles", tags=["admin · roles"])


RoleIdPath = Annotated[str, Path(min_length=1, description="Role UUID")]


@router.get(
    "/active",
    response_model=list[RoleOption],
    dependencies=[Depends(RequirePermission("ROLES_VIEW"))],
)
async def list_active_roles(db: DBSession) -> list[RoleOption]:
    return await role_service.list_active(db)


@router.get(
    "/{role_id}",
    response_model=SingleResponse[RoleDetail],
    dependencies=[Depends(RequirePermission("ROLES_VIEW"))],
)
async def get_role(role_id: RoleIdPath, db: DBSession) -> SingleResponse[RoleDetail]:
    return await role_service.get_by_id(db, role_id)


@router.post(
    "/list",
    response_model=PaginatedResponse[RoleItem],
    dependencies=[Depends(RequirePermission("ROLES_VIEW"))],
)
async def list_roles(query: QueryRequest, db: DBSession) -> PaginatedResponse[RoleItem]:
    return await role_service.list_paginated(db, query)


@router.post(
    "",
    response_model=SingleResponse[RoleDetail],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RequirePermission("ROLES_CREATE"))],
)
async def create_role(
    payload: RoleCreate, db: DBSession, actor: CurrentAuth
) -> SingleResponse[RoleDetail]:
    return await role_service.create(db, payload, actor_id=actor.id)


@router.put(
    "/{role_id}",
    response_model=SingleResponse[RoleDetail],
    dependencies=[Depends(RequirePermission("ROLES_UPDATE"))],
)
async def update_role(
    role_id: RoleIdPath,
    payload: RoleUpdate,
    db: DBSession,
    actor: CurrentAuth,
) -> SingleResponse[RoleDetail]:
    return await role_service.update(db, role_id, payload, actor_id=actor.id)
