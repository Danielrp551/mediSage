"""
Office CRUD endpoints. Permission gating via `dependencies=[...]` at the
decorator (per fastapi skill + template convention). `actor: CurrentAuth` is
requested separately when the handler needs the user id for audit columns.

`/active` is declared before `/{office_id}` so the literal path isn't captured
by the id route. It accepts optional `branch_id` / `vertical_id` query params so
the Offices list (filter by branch) and scheduling (apt offices for a vertical)
can scope the dropdown. `/list` is POST + body (`QueryRequest`).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from app.core.dependencies import CurrentAuth, DBSession, RequirePermission
from app.modules.clinic.schemas.office import (
    OfficeCreate,
    OfficeDetail,
    OfficeItem,
    OfficeOption,
    OfficeUpdate,
)
from app.modules.clinic.services import office as office_service
from app.shared.base_schemas import PaginatedResponse, QueryRequest, SingleResponse

router = APIRouter(prefix="/offices", tags=["clinic · offices"])


OfficeIdPath = Annotated[str, Path(min_length=1, description="Office UUID")]


@router.get(
    "/active",
    response_model=list[OfficeOption],
    dependencies=[Depends(RequirePermission("OFFICES_READ"))],
)
async def list_active_offices(
    db: DBSession,
    branch_id: str | None = None,
    vertical_id: str | None = None,
) -> list[OfficeOption]:
    return await office_service.list_active(db, branch_id=branch_id, vertical_id=vertical_id)


@router.post(
    "/list",
    response_model=PaginatedResponse[OfficeItem],
    dependencies=[Depends(RequirePermission("OFFICES_READ"))],
)
async def list_offices(query: QueryRequest, db: DBSession) -> PaginatedResponse[OfficeItem]:
    return await office_service.list_paginated(db, query)


@router.post(
    "",
    response_model=SingleResponse[OfficeDetail],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RequirePermission("OFFICES_CREATE"))],
)
async def create_office(
    payload: OfficeCreate, db: DBSession, actor: CurrentAuth
) -> SingleResponse[OfficeDetail]:
    return await office_service.create(db, payload, actor_id=actor.id)


@router.get(
    "/{office_id}",
    response_model=SingleResponse[OfficeDetail],
    dependencies=[Depends(RequirePermission("OFFICES_READ"))],
)
async def get_office(office_id: OfficeIdPath, db: DBSession) -> SingleResponse[OfficeDetail]:
    return await office_service.get_by_id(db, office_id)


@router.put(
    "/{office_id}",
    response_model=SingleResponse[OfficeDetail],
    dependencies=[Depends(RequirePermission("OFFICES_UPDATE"))],
)
async def update_office(
    office_id: OfficeIdPath,
    payload: OfficeUpdate,
    db: DBSession,
    actor: CurrentAuth,
) -> SingleResponse[OfficeDetail]:
    return await office_service.update(db, office_id, payload, actor_id=actor.id)


@router.delete(
    "/{office_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(RequirePermission("OFFICES_DELETE"))],
)
async def delete_office(office_id: OfficeIdPath, db: DBSession, actor: CurrentAuth) -> None:
    await office_service.soft_delete(db, office_id, actor_id=actor.id)
