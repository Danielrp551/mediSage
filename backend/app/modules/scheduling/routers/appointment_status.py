"""
Router del catálogo AppointmentStatus (+ matriz de transiciones). `/active` antes de
las rutas dinámicas. Permisos: APPOINTMENT_STATUSES_READ (lectura) /
APPOINTMENT_STATUSES_WRITE (CRUD + editar la matriz). El service devuelve los
envelopes; `/active` devuelve lista cruda (sin envelope), consistente con el resto
de los catálogos (catalog/clinic/staff/crm).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from app.core.dependencies import CurrentAuth, DBSession, RequirePermission
from app.modules.scheduling.schemas.appointment_status import (
    AppointmentStatusCreate,
    AppointmentStatusItem,
    AppointmentStatusOption,
    AppointmentStatusUpdate,
    StatusTransitionUpdate,
    TransitionTargets,
)
from app.modules.scheduling.services import appointment_status as appointment_status_service
from app.shared.base_schemas import PaginatedResponse, QueryRequest, SingleResponse

router = APIRouter(prefix="/appointment-statuses", tags=["scheduling · appointment statuses"])

StatusIdPath = Annotated[str, Path(min_length=1, description="AppointmentStatus UUID")]


@router.get(
    "/active",
    response_model=list[AppointmentStatusOption],
    dependencies=[Depends(RequirePermission("APPOINTMENT_STATUSES_READ"))],
)
async def list_active_appointment_statuses(db: DBSession) -> list[AppointmentStatusOption]:
    return await appointment_status_service.list_active(db)


@router.post(
    "/list",
    response_model=PaginatedResponse[AppointmentStatusItem],
    dependencies=[Depends(RequirePermission("APPOINTMENT_STATUSES_READ"))],
)
async def list_appointment_statuses(
    query: QueryRequest, db: DBSession
) -> PaginatedResponse[AppointmentStatusItem]:
    return await appointment_status_service.list_paginated(db, query)


@router.post(
    "",
    response_model=SingleResponse[AppointmentStatusItem],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RequirePermission("APPOINTMENT_STATUSES_WRITE"))],
)
async def create_appointment_status(
    payload: AppointmentStatusCreate, db: DBSession, actor: CurrentAuth
) -> SingleResponse[AppointmentStatusItem]:
    return await appointment_status_service.create(db, payload, actor_id=actor.id)


@router.put(
    "/{status_id}",
    response_model=SingleResponse[AppointmentStatusItem],
    dependencies=[Depends(RequirePermission("APPOINTMENT_STATUSES_WRITE"))],
)
async def update_appointment_status(
    status_id: StatusIdPath,
    payload: AppointmentStatusUpdate,
    db: DBSession,
    actor: CurrentAuth,
) -> SingleResponse[AppointmentStatusItem]:
    return await appointment_status_service.update(db, status_id, payload, actor_id=actor.id)


@router.delete(
    "/{status_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(RequirePermission("APPOINTMENT_STATUSES_WRITE"))],
)
async def delete_appointment_status(
    status_id: StatusIdPath, db: DBSession, actor: CurrentAuth
) -> None:
    await appointment_status_service.remove(db, status_id, actor_id=actor.id)


@router.get(
    "/{status_id}/transitions",
    response_model=SingleResponse[TransitionTargets],
    dependencies=[Depends(RequirePermission("APPOINTMENT_STATUSES_READ"))],
)
async def get_appointment_status_transitions(
    status_id: StatusIdPath, db: DBSession
) -> SingleResponse[TransitionTargets]:
    return await appointment_status_service.get_transitions(db, status_id)


@router.put(
    "/{status_id}/transitions",
    response_model=SingleResponse[TransitionTargets],
    dependencies=[Depends(RequirePermission("APPOINTMENT_STATUSES_WRITE"))],
)
async def set_appointment_status_transitions(
    status_id: StatusIdPath,
    payload: StatusTransitionUpdate,
    db: DBSession,
    actor: CurrentAuth,
) -> SingleResponse[TransitionTargets]:
    return await appointment_status_service.set_transitions(
        db, status_id, payload, actor_id=actor.id
    )
