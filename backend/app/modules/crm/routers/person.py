"""
Endpoints CRUD de Person. Gating de permisos vía `dependencies=[...]` en el
decorator; `actor: CurrentAuth` aparte cuando el handler necesita el id para las
columnas de audit.

`/active` y `/search` se declaran ANTES de `/{person_id}` para que los paths
literales no los capture la ruta dinámica del id. `/active` devuelve la lista
cruda (`PersonOption`). Filtros por estado/asesor llegan como query params
deep-link (no-op en F1; el listado paginado los acepta para no romper el front).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status

from app.core.dependencies import CurrentAuth, DBSession, RequirePermission
from app.modules.crm.schemas.person import (
    PersonCreate,
    PersonDetail,
    PersonItem,
    PersonOption,
    PersonUpdate,
)
from app.modules.crm.services import person as person_service
from app.shared.base_schemas import PaginatedResponse, QueryRequest, SingleResponse

router = APIRouter(prefix="/persons", tags=["crm · persons"])


PersonIdPath = Annotated[str, Path(min_length=1, description="Person UUID")]


@router.get(
    "/active",
    response_model=list[PersonOption],
    dependencies=[Depends(RequirePermission("PERSONS_READ"))],
)
async def list_active_persons(db: DBSession) -> list[PersonOption]:
    return await person_service.list_active(db)


@router.get(
    "/search",
    response_model=SingleResponse[list[PersonOption]],
    dependencies=[Depends(RequirePermission("PERSONS_READ"))],
)
async def search_persons(
    db: DBSession,
    q: Annotated[str | None, Query()] = None,
    channel_type: Annotated[str | None, Query()] = None,
    identifier: Annotated[str | None, Query()] = None,
) -> SingleResponse[list[PersonOption]]:
    return await person_service.search(db, q=q, channel_type=channel_type, identifier=identifier)


@router.post(
    "/list",
    response_model=PaginatedResponse[PersonItem],
    dependencies=[Depends(RequirePermission("PERSONS_READ"))],
)
async def list_persons(
    query: QueryRequest,
    db: DBSession,
    lead_status_id: Annotated[str | None, Query()] = None,
    customer_status_id: Annotated[str | None, Query()] = None,
    advisor_user_id: Annotated[str | None, Query()] = None,
    has_active_lead: Annotated[bool | None, Query()] = None,
) -> PaginatedResponse[PersonItem]:
    return await person_service.list_paginated(
        db,
        query,
        lead_status_id=lead_status_id,
        customer_status_id=customer_status_id,
        advisor_user_id=advisor_user_id,
        has_active_lead=has_active_lead,
    )


@router.post(
    "",
    response_model=SingleResponse[PersonDetail],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RequirePermission("PERSONS_CREATE"))],
)
async def create_person(
    payload: PersonCreate, db: DBSession, actor: CurrentAuth
) -> SingleResponse[PersonDetail]:
    return await person_service.create(db, payload, actor_id=actor.id)


@router.get(
    "/{person_id}",
    response_model=SingleResponse[PersonDetail],
    dependencies=[Depends(RequirePermission("PERSONS_READ"))],
)
async def get_person(person_id: PersonIdPath, db: DBSession) -> SingleResponse[PersonDetail]:
    return await person_service.get_by_id(db, person_id)


@router.put(
    "/{person_id}",
    response_model=SingleResponse[PersonDetail],
    dependencies=[Depends(RequirePermission("PERSONS_UPDATE"))],
)
async def update_person(
    person_id: PersonIdPath,
    payload: PersonUpdate,
    db: DBSession,
    actor: CurrentAuth,
) -> SingleResponse[PersonDetail]:
    return await person_service.update(db, person_id, payload, actor_id=actor.id)


@router.delete(
    "/{person_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(RequirePermission("PERSONS_DELETE"))],
)
async def delete_person(person_id: PersonIdPath, db: DBSession, actor: CurrentAuth) -> None:
    await person_service.soft_delete(db, person_id, actor_id=actor.id)
