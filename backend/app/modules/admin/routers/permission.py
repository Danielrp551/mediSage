from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from app.core.dependencies import CurrentAuth, DBSession, RequirePermission
from app.modules.admin.schemas.permission import (
    PermissionCreate,
    PermissionItem,
    PermissionOption,
    PermissionUpdate,
)
from app.modules.admin.services import permission as permission_service
from app.shared.base_schemas import PaginatedResponse, QueryRequest, SingleResponse

router = APIRouter(prefix="/permissions", tags=["admin · permissions"])


PermissionIdPath = Annotated[str, Path(min_length=1, description="Permission UUID")]


@router.get(
    "/active",
    response_model=list[PermissionOption],
    dependencies=[Depends(RequirePermission("PERMISSIONS_VIEW"))],
)
async def list_active_permissions(db: DBSession) -> list[PermissionOption]:
    return await permission_service.list_active(db)


@router.get(
    "/{permission_id}",
    response_model=SingleResponse[PermissionItem],
    dependencies=[Depends(RequirePermission("PERMISSIONS_VIEW"))],
)
async def get_permission(
    permission_id: PermissionIdPath, db: DBSession
) -> SingleResponse[PermissionItem]:
    return await permission_service.get_by_id(db, permission_id)


@router.post(
    "/list",
    response_model=PaginatedResponse[PermissionItem],
    dependencies=[Depends(RequirePermission("PERMISSIONS_VIEW"))],
)
async def list_permissions(query: QueryRequest, db: DBSession) -> PaginatedResponse[PermissionItem]:
    return await permission_service.list_paginated(db, query)


@router.post(
    "",
    response_model=SingleResponse[PermissionItem],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RequirePermission("PERMISSIONS_CREATE"))],
)
async def create_permission(
    payload: PermissionCreate, db: DBSession, actor: CurrentAuth
) -> SingleResponse[PermissionItem]:
    return await permission_service.create(db, payload, actor_id=actor.id)


@router.put(
    "/{permission_id}",
    response_model=SingleResponse[PermissionItem],
    dependencies=[Depends(RequirePermission("PERMISSIONS_UPDATE"))],
)
async def update_permission(
    permission_id: PermissionIdPath,
    payload: PermissionUpdate,
    db: DBSession,
    actor: CurrentAuth,
) -> SingleResponse[PermissionItem]:
    return await permission_service.update(db, permission_id, payload, actor_id=actor.id)
