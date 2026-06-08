"""
Self-service del doctor. F2: /me/appointments/list (su agenda, scoped al doctor del
user logueado vía el service → anti-IDOR). /me/calendar (grilla) llega en F4.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.dependencies import CurrentAuth, DBSession, RequirePermission
from app.modules.scheduling.schemas.appointment import AppointmentItem
from app.modules.scheduling.services import appointment as appt_service
from app.shared.base_schemas import PaginatedResponse, QueryRequest

router = APIRouter(prefix="/me", tags=["scheduling · me"])


@router.post(
    "/appointments/list",
    response_model=PaginatedResponse[AppointmentItem],
    dependencies=[Depends(RequirePermission("MY_APPOINTMENTS_READ"))],
)
async def list_my_appointments(
    query: QueryRequest, db: DBSession, actor: CurrentAuth
) -> PaginatedResponse[AppointmentItem]:
    return await appt_service.list_for_current_doctor(db, query, user_id=actor.id)
