"""
Router de citas. F2: list (APPOINTMENTS_READ) + create/book (APPOINTMENTS_CREATE) +
get detalle (APPOINTMENTS_READ). El lifecycle (transition/shortcuts/cancel/reschedule),
el update (PUT) y el calendario llegan en fases siguientes (F3/F4) — cuando se agregue
`/calendar`, declararlo ANTES de `/{appointment_id}`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from app.core.dependencies import CurrentAuth, DBSession, RequirePermission
from app.modules.scheduling.schemas.appointment import (
    AppointmentCreate,
    AppointmentDetail,
    AppointmentItem,
)
from app.modules.scheduling.services import appointment as appt_service
from app.shared.base_schemas import PaginatedResponse, QueryRequest, SingleResponse

router = APIRouter(prefix="/appointments", tags=["scheduling · appointments"])

ApptIdPath = Annotated[str, Path(min_length=1, description="Appointment UUID")]


@router.post(
    "/list",
    response_model=PaginatedResponse[AppointmentItem],
    dependencies=[Depends(RequirePermission("APPOINTMENTS_READ"))],
)
async def list_appointments(
    query: QueryRequest, db: DBSession
) -> PaginatedResponse[AppointmentItem]:
    return await appt_service.list_paginated(db, query)


@router.post(
    "",
    response_model=SingleResponse[AppointmentDetail],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RequirePermission("APPOINTMENTS_CREATE"))],
)
async def create_appointment(
    payload: AppointmentCreate, db: DBSession, actor: CurrentAuth
) -> SingleResponse[AppointmentDetail]:
    return await appt_service.create_appointment(db, payload, actor_id=actor.id)


@router.get(
    "/{appointment_id}",
    response_model=SingleResponse[AppointmentDetail],
    dependencies=[Depends(RequirePermission("APPOINTMENTS_READ"))],
)
async def get_appointment(
    appointment_id: ApptIdPath, db: DBSession
) -> SingleResponse[AppointmentDetail]:
    return await appt_service.get_by_id(db, appointment_id)
