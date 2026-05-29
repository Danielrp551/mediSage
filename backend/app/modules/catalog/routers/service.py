"""
Service CRUD endpoints. Permission gating via `dependencies=[...]` at the
decorator (per fastapi skill + template convention). `actor: CurrentAuth`
is requested separately when the handler needs the user id for audit
columns.

`/active` accepts an optional `vertical_id` query param so the Products
page (phase 3) and the Service drawer can scope the dropdown to one
vertical.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from app.core.dependencies import CurrentAuth, DBSession, RequirePermission
from app.modules.catalog.schemas.service import (
    ServiceCreate,
    ServiceDetail,
    ServiceItem,
    ServiceOption,
    ServiceUpdate,
)
from app.modules.catalog.services import service as service_service
from app.shared.base_schemas import PaginatedResponse, QueryRequest, SingleResponse

router = APIRouter(prefix="/services", tags=["catalog · services"])


ServiceIdPath = Annotated[str, Path(min_length=1, description="Service UUID")]


@router.get(
    "/active",
    response_model=list[ServiceOption],
    dependencies=[Depends(RequirePermission("SERVICES_READ"))],
)
async def list_active_services(
    db: DBSession, vertical_id: str | None = None
) -> list[ServiceOption]:
    return await service_service.list_active(db, vertical_id=vertical_id)


@router.post(
    "/list",
    response_model=PaginatedResponse[ServiceItem],
    dependencies=[Depends(RequirePermission("SERVICES_READ"))],
)
async def list_services(query: QueryRequest, db: DBSession) -> PaginatedResponse[ServiceItem]:
    return await service_service.list_paginated(db, query)


@router.post(
    "",
    response_model=SingleResponse[ServiceDetail],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RequirePermission("SERVICES_CREATE"))],
)
async def create_service(
    payload: ServiceCreate, db: DBSession, actor: CurrentAuth
) -> SingleResponse[ServiceDetail]:
    return await service_service.create(db, payload, actor_id=actor.id)


@router.get(
    "/{service_id}",
    response_model=SingleResponse[ServiceDetail],
    dependencies=[Depends(RequirePermission("SERVICES_READ"))],
)
async def get_service(service_id: ServiceIdPath, db: DBSession) -> SingleResponse[ServiceDetail]:
    return await service_service.get_by_id(db, service_id)


@router.put(
    "/{service_id}",
    response_model=SingleResponse[ServiceDetail],
    dependencies=[Depends(RequirePermission("SERVICES_UPDATE"))],
)
async def update_service(
    service_id: ServiceIdPath,
    payload: ServiceUpdate,
    db: DBSession,
    actor: CurrentAuth,
) -> SingleResponse[ServiceDetail]:
    return await service_service.update(db, service_id, payload, actor_id=actor.id)


@router.delete(
    "/{service_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(RequirePermission("SERVICES_DELETE"))],
)
async def delete_service(service_id: ServiceIdPath, db: DBSession, actor: CurrentAuth) -> None:
    await service_service.soft_delete(db, service_id, actor_id=actor.id)
