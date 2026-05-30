"""
Endpoints CRUD de Doctor. Gating de permisos vía `dependencies=[...]` en el
decorator (skill fastapi + convención del template). `actor: CurrentAuth` se pide
aparte cuando el handler necesita el id del usuario para las columnas de audit.

`/active` se declara antes de `/{doctor_id}` para que el path literal no lo
capture la ruta del id. Acepta `branch_id`/`vertical_id` opcionales para acotar
el dropdown. `/list` es POST + body (`QueryRequest`). Create devuelve
`DoctorCreatedResponse` (con `generated_password`), igual que admin.users.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from app.core.dependencies import CurrentAuth, DBSession, RequirePermission
from app.modules.staff.schemas.doctor import (
    DoctorCreate,
    DoctorCreatedResponse,
    DoctorDetail,
    DoctorItem,
    DoctorOption,
    DoctorUpdate,
)
from app.modules.staff.services import doctor as doctor_service
from app.shared.base_schemas import PaginatedResponse, QueryRequest, SingleResponse

router = APIRouter(prefix="/doctors", tags=["staff · doctors"])


DoctorIdPath = Annotated[str, Path(min_length=1, description="Doctor UUID")]


@router.get(
    "/active",
    response_model=list[DoctorOption],
    dependencies=[Depends(RequirePermission("DOCTORS_READ"))],
)
async def list_active_doctors(
    db: DBSession,
    branch_id: str | None = None,
    vertical_id: str | None = None,
) -> list[DoctorOption]:
    return await doctor_service.list_active(db, branch_id=branch_id, vertical_id=vertical_id)


@router.post(
    "/list",
    response_model=PaginatedResponse[DoctorItem],
    dependencies=[Depends(RequirePermission("DOCTORS_READ"))],
)
async def list_doctors(query: QueryRequest, db: DBSession) -> PaginatedResponse[DoctorItem]:
    return await doctor_service.list_paginated(db, query)


@router.post(
    "",
    response_model=DoctorCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RequirePermission("DOCTORS_CREATE"))],
)
async def create_doctor(
    payload: DoctorCreate, db: DBSession, actor: CurrentAuth
) -> DoctorCreatedResponse:
    return await doctor_service.create(db, payload, actor_id=actor.id)


@router.get(
    "/{doctor_id}",
    response_model=SingleResponse[DoctorDetail],
    dependencies=[Depends(RequirePermission("DOCTORS_READ"))],
)
async def get_doctor(doctor_id: DoctorIdPath, db: DBSession) -> SingleResponse[DoctorDetail]:
    return await doctor_service.get_by_id(db, doctor_id)


@router.put(
    "/{doctor_id}",
    response_model=SingleResponse[DoctorDetail],
    dependencies=[Depends(RequirePermission("DOCTORS_UPDATE"))],
)
async def update_doctor(
    doctor_id: DoctorIdPath,
    payload: DoctorUpdate,
    db: DBSession,
    actor: CurrentAuth,
) -> SingleResponse[DoctorDetail]:
    return await doctor_service.update(db, doctor_id, payload, actor_id=actor.id)


@router.delete(
    "/{doctor_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(RequirePermission("DOCTORS_DELETE"))],
)
async def delete_doctor(doctor_id: DoctorIdPath, db: DBSession, actor: CurrentAuth) -> None:
    await doctor_service.soft_delete(db, doctor_id, actor_id=actor.id)
