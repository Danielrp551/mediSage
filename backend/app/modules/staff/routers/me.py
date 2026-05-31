"""
Self-service `/me` del doctor logueado (F3). El doctor gestiona SU perfil
profesional + SU disponibilidad. El doctor se resuelve desde el token
(`CurrentAuth`) en el service; los permisos `MY_*` los aplica el decorator.

Mismas formas de respuesta que los endpoints admin equivalentes — solo cambian
el permiso y que el doctor es siempre el logueado (403 NOT_A_DOCTOR si no tiene
perfil).
"""

from __future__ import annotations

from datetime import date as date_type
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status

from app.core.dependencies import CurrentAuth, DBSession, RequirePermission
from app.modules.staff.schemas.doctor import DoctorDetail, DoctorSelfUpdate
from app.modules.staff.schemas.doctor_availability import (
    DoctorAvailabilityBulkCreate,
    DoctorAvailabilityItem,
    DoctorAvailabilityUpdate,
)
from app.modules.staff.services import me as me_service
from app.shared.base_schemas import SingleResponse

router = APIRouter(prefix="/me", tags=["staff · me (self-service)"])


BlockIdPath = Annotated[str, Path(min_length=1, description="Availability block UUID")]


@router.get(
    "/doctor",
    response_model=SingleResponse[DoctorDetail],
    dependencies=[Depends(RequirePermission("MY_DOCTOR_PROFILE_READ"))],
)
async def get_my_doctor(db: DBSession, auth: CurrentAuth) -> SingleResponse[DoctorDetail]:
    return await me_service.get_my_doctor(db, auth)


@router.put(
    "/doctor",
    response_model=SingleResponse[DoctorDetail],
    dependencies=[Depends(RequirePermission("MY_DOCTOR_PROFILE_WRITE"))],
)
async def update_my_doctor(
    payload: DoctorSelfUpdate, db: DBSession, auth: CurrentAuth
) -> SingleResponse[DoctorDetail]:
    return await me_service.update_my_doctor(db, auth, payload)


@router.get(
    "/availability",
    response_model=SingleResponse[list[DoctorAvailabilityItem]],
    dependencies=[Depends(RequirePermission("MY_AVAILABILITY_READ"))],
)
async def list_my_availability(
    db: DBSession,
    auth: CurrentAuth,
    date_from: Annotated[date_type | None, Query(alias="from")] = None,
    date_to: Annotated[date_type | None, Query(alias="to")] = None,
) -> SingleResponse[list[DoctorAvailabilityItem]]:
    return await me_service.list_my_availability(db, auth, date_from, date_to)


@router.post(
    "/availability",
    response_model=SingleResponse[list[DoctorAvailabilityItem]],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RequirePermission("MY_AVAILABILITY_WRITE"))],
)
async def create_my_availability(
    payload: DoctorAvailabilityBulkCreate, db: DBSession, auth: CurrentAuth
) -> SingleResponse[list[DoctorAvailabilityItem]]:
    return await me_service.create_my_availability(db, auth, payload)


@router.put(
    "/availability/{block_id}",
    response_model=SingleResponse[DoctorAvailabilityItem],
    dependencies=[Depends(RequirePermission("MY_AVAILABILITY_WRITE"))],
)
async def update_my_availability(
    block_id: BlockIdPath,
    payload: DoctorAvailabilityUpdate,
    db: DBSession,
    auth: CurrentAuth,
) -> SingleResponse[DoctorAvailabilityItem]:
    return await me_service.update_my_availability(db, auth, block_id, payload)


@router.delete(
    "/availability/{block_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(RequirePermission("MY_AVAILABILITY_WRITE"))],
)
async def delete_my_availability(block_id: BlockIdPath, db: DBSession, auth: CurrentAuth) -> None:
    await me_service.delete_my_availability(db, auth, block_id)
