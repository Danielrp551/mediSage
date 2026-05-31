"""
Endpoints de disponibilidad de un doctor, anidados bajo
`/doctors/{doctor_id}/availability`. Alta MASIVA (POST bulk), edición/borrado por
bloque (PUT/DELETE con ownership). Gating por permiso en el decorator; `actor`
aparte para las columnas de audit.

`from`/`to` (query, `date` ISO) filtran el rango de fechas del GET. `from`/`to`
son palabras/identificadores cómodos en el cliente; acá se reciben con alias.
"""

from __future__ import annotations

from datetime import date as date_type
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status

from app.core.dependencies import CurrentAuth, DBSession, RequirePermission
from app.modules.staff.schemas.doctor_availability import (
    DoctorAvailabilityBulkCreate,
    DoctorAvailabilityItem,
    DoctorAvailabilityUpdate,
)
from app.modules.staff.services import doctor_availability as availability_service
from app.shared.base_schemas import SingleResponse

router = APIRouter(prefix="/doctors/{doctor_id}/availability", tags=["staff · availability"])


DoctorIdPath = Annotated[str, Path(min_length=1, description="Doctor UUID")]
BlockIdPath = Annotated[str, Path(min_length=1, description="Availability block UUID")]


@router.get(
    "",
    response_model=SingleResponse[list[DoctorAvailabilityItem]],
    dependencies=[Depends(RequirePermission("DOCTOR_AVAILABILITY_READ"))],
)
async def list_availability(
    doctor_id: DoctorIdPath,
    db: DBSession,
    date_from: Annotated[date_type | None, Query(alias="from")] = None,
    date_to: Annotated[date_type | None, Query(alias="to")] = None,
) -> SingleResponse[list[DoctorAvailabilityItem]]:
    return await availability_service.list_for_doctor(db, doctor_id, date_from, date_to)


@router.post(
    "",
    response_model=SingleResponse[list[DoctorAvailabilityItem]],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RequirePermission("DOCTOR_AVAILABILITY_WRITE"))],
)
async def create_availability(
    doctor_id: DoctorIdPath,
    payload: DoctorAvailabilityBulkCreate,
    db: DBSession,
    actor: CurrentAuth,
) -> SingleResponse[list[DoctorAvailabilityItem]]:
    return await availability_service.bulk_create(db, doctor_id, payload, actor_id=actor.id)


@router.put(
    "/{block_id}",
    response_model=SingleResponse[DoctorAvailabilityItem],
    dependencies=[Depends(RequirePermission("DOCTOR_AVAILABILITY_WRITE"))],
)
async def update_availability(
    doctor_id: DoctorIdPath,
    block_id: BlockIdPath,
    payload: DoctorAvailabilityUpdate,
    db: DBSession,
    actor: CurrentAuth,
) -> SingleResponse[DoctorAvailabilityItem]:
    return await availability_service.update_block(
        db, doctor_id, block_id, payload, actor_id=actor.id
    )


@router.delete(
    "/{block_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(RequirePermission("DOCTOR_AVAILABILITY_WRITE"))],
)
async def delete_availability(
    doctor_id: DoctorIdPath,
    block_id: BlockIdPath,
    db: DBSession,
    actor: CurrentAuth,
) -> None:
    await availability_service.delete_block(db, doctor_id, block_id, actor_id=actor.id)
