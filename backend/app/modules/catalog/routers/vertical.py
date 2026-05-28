"""
Vertical CRUD endpoints. Permission gating via `dependencies=[...]` at the
decorator (per fastapi skill + template convention). `actor: CurrentAuth`
is requested separately when the handler needs the user id for audit
columns.

`/list` is POST + body (`QueryRequest`) because the filter payload can be
arbitrarily large — GET with query-string would not survive complex
filter groups.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from app.core.dependencies import CurrentAuth, DBSession, RequirePermission
from app.modules.catalog.schemas.vertical import (
    VerticalCreate,
    VerticalDetail,
    VerticalItem,
    VerticalOption,
    VerticalUpdate,
)
from app.modules.catalog.services import vertical as vertical_service
from app.shared.base_schemas import PaginatedResponse, QueryRequest, SingleResponse

router = APIRouter(prefix="/verticals", tags=["catalog · verticals"])


VerticalIdPath = Annotated[str, Path(min_length=1, description="Vertical UUID")]


@router.get(
    "/active",
    response_model=list[VerticalOption],
    dependencies=[Depends(RequirePermission("VERTICALS_READ"))],
)
async def list_active_verticals(db: DBSession) -> list[VerticalOption]:
    return await vertical_service.list_active(db)


@router.post(
    "/list",
    response_model=PaginatedResponse[VerticalItem],
    dependencies=[Depends(RequirePermission("VERTICALS_READ"))],
)
async def list_verticals(query: QueryRequest, db: DBSession) -> PaginatedResponse[VerticalItem]:
    return await vertical_service.list_paginated(db, query)


@router.post(
    "",
    response_model=SingleResponse[VerticalDetail],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RequirePermission("VERTICALS_CREATE"))],
)
async def create_vertical(
    payload: VerticalCreate, db: DBSession, actor: CurrentAuth
) -> SingleResponse[VerticalDetail]:
    return await vertical_service.create(db, payload, actor_id=actor.id)


@router.get(
    "/{vertical_id}",
    response_model=SingleResponse[VerticalDetail],
    dependencies=[Depends(RequirePermission("VERTICALS_READ"))],
)
async def get_vertical(
    vertical_id: VerticalIdPath, db: DBSession
) -> SingleResponse[VerticalDetail]:
    return await vertical_service.get_by_id(db, vertical_id)


@router.put(
    "/{vertical_id}",
    response_model=SingleResponse[VerticalDetail],
    dependencies=[Depends(RequirePermission("VERTICALS_UPDATE"))],
)
async def update_vertical(
    vertical_id: VerticalIdPath,
    payload: VerticalUpdate,
    db: DBSession,
    actor: CurrentAuth,
) -> SingleResponse[VerticalDetail]:
    return await vertical_service.update(db, vertical_id, payload, actor_id=actor.id)


@router.delete(
    "/{vertical_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(RequirePermission("VERTICALS_DELETE"))],
)
async def delete_vertical(vertical_id: VerticalIdPath, db: DBSession, actor: CurrentAuth) -> None:
    await vertical_service.soft_delete(db, vertical_id, actor_id=actor.id)
