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
    AppointmentCancelRequest,
    AppointmentCreate,
    AppointmentDetail,
    AppointmentItem,
    AppointmentRescheduleRequest,
    AppointmentTransitionRequest,
    AppointmentUpdate,
)
from app.modules.scheduling.services import appointment as appt_service
from app.modules.scheduling.services import transition as transition_service
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


@router.put(
    "/{appointment_id}",
    response_model=SingleResponse[AppointmentDetail],
    dependencies=[Depends(RequirePermission("APPOINTMENTS_UPDATE"))],
)
async def update_appointment(
    appointment_id: ApptIdPath,
    payload: AppointmentUpdate,
    db: DBSession,
    actor: CurrentAuth,
) -> SingleResponse[AppointmentDetail]:
    return await appt_service.update_appointment(db, appointment_id, payload, actor_id=actor.id)


@router.delete(
    "/{appointment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(RequirePermission("APPOINTMENTS_DELETE"))],
)
async def delete_appointment(appointment_id: ApptIdPath, db: DBSession, actor: CurrentAuth) -> None:
    await appt_service.delete_appointment(db, appointment_id, actor_id=actor.id)


# ── Lifecycle: transición genérica + shortcuts (F3) ───────────────────


@router.post(
    "/{appointment_id}/transition",
    response_model=SingleResponse[AppointmentDetail],
    dependencies=[Depends(RequirePermission("APPOINTMENTS_TRANSITION"))],
)
async def transition_appointment(
    appointment_id: ApptIdPath,
    payload: AppointmentTransitionRequest,
    db: DBSession,
    actor: CurrentAuth,
) -> SingleResponse[AppointmentDetail]:
    return await transition_service.transition(
        db, appointment_id, payload.to_status_id, actor_id=actor.id, reason=payload.reason
    )


@router.post(
    "/{appointment_id}/confirm",
    response_model=SingleResponse[AppointmentDetail],
    dependencies=[Depends(RequirePermission("APPOINTMENTS_TRANSITION"))],
)
async def confirm_appointment(
    appointment_id: ApptIdPath, db: DBSession, actor: CurrentAuth
) -> SingleResponse[AppointmentDetail]:
    return await transition_service.confirm(db, appointment_id, actor_id=actor.id)


@router.post(
    "/{appointment_id}/check-in",
    response_model=SingleResponse[AppointmentDetail],
    dependencies=[Depends(RequirePermission("APPOINTMENTS_TRANSITION"))],
)
async def check_in_appointment(
    appointment_id: ApptIdPath, db: DBSession, actor: CurrentAuth
) -> SingleResponse[AppointmentDetail]:
    return await transition_service.check_in(db, appointment_id, actor_id=actor.id)


@router.post(
    "/{appointment_id}/start",
    response_model=SingleResponse[AppointmentDetail],
    dependencies=[Depends(RequirePermission("APPOINTMENTS_TRANSITION"))],
)
async def start_appointment(
    appointment_id: ApptIdPath, db: DBSession, actor: CurrentAuth
) -> SingleResponse[AppointmentDetail]:
    return await transition_service.start(db, appointment_id, actor_id=actor.id)


@router.post(
    "/{appointment_id}/attend",
    response_model=SingleResponse[AppointmentDetail],
    dependencies=[Depends(RequirePermission("APPOINTMENTS_TRANSITION"))],
)
async def attend_appointment(
    appointment_id: ApptIdPath, db: DBSession, actor: CurrentAuth
) -> SingleResponse[AppointmentDetail]:
    return await transition_service.attend(db, appointment_id, actor_id=actor.id)


@router.post(
    "/{appointment_id}/no-show",
    response_model=SingleResponse[AppointmentDetail],
    dependencies=[Depends(RequirePermission("APPOINTMENTS_TRANSITION"))],
)
async def no_show_appointment(
    appointment_id: ApptIdPath, db: DBSession, actor: CurrentAuth
) -> SingleResponse[AppointmentDetail]:
    return await transition_service.no_show(db, appointment_id, actor_id=actor.id)


@router.post(
    "/{appointment_id}/cancel",
    response_model=SingleResponse[AppointmentDetail],
    dependencies=[Depends(RequirePermission("APPOINTMENTS_CANCEL"))],
)
async def cancel_appointment(
    appointment_id: ApptIdPath,
    payload: AppointmentCancelRequest,
    db: DBSession,
    actor: CurrentAuth,
) -> SingleResponse[AppointmentDetail]:
    # El override de min_hours_to_cancel se evalúa en el service (necesita
    # actor.permissions) — por eso pasa el AuthContext completo, no solo el id.
    return await transition_service.cancel(db, appointment_id, payload, actor=actor)


@router.post(
    "/{appointment_id}/reschedule",
    response_model=SingleResponse[AppointmentDetail],
    dependencies=[Depends(RequirePermission("APPOINTMENTS_RESCHEDULE"))],
)
async def reschedule_appointment(
    appointment_id: ApptIdPath,
    payload: AppointmentRescheduleRequest,
    db: DBSession,
    actor: CurrentAuth,
) -> SingleResponse[AppointmentDetail]:
    return await transition_service.reschedule(db, appointment_id, payload, actor_id=actor.id)
