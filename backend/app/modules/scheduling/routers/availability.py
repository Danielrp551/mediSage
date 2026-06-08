"""
Router de disponibilidad on-the-fly. POST /compute (slots libres en un rango) +
POST /check-slot (revalida un slot puntual). Ambos gated por AVAILABILITY_READ (lo
tienen ASESOR y DOCTOR). Read-only: NO crean nada.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.dependencies import DBSession, RequirePermission
from app.modules.scheduling.schemas.availability import (
    AvailabilityRequest,
    AvailabilityResponse,
    CheckSlotRequest,
    CheckSlotResponse,
)
from app.modules.scheduling.services import availability as availability_service
from app.shared.base_schemas import SingleResponse

router = APIRouter(prefix="/availability", tags=["scheduling · availability"])


@router.post(
    "/compute",
    response_model=SingleResponse[AvailabilityResponse],
    dependencies=[Depends(RequirePermission("AVAILABILITY_READ"))],
)
async def compute_availability(
    payload: AvailabilityRequest, db: DBSession
) -> SingleResponse[AvailabilityResponse]:
    data = await availability_service.compute_available_slots(
        db,
        doctor_id=payload.doctor_id,
        product_id=payload.product_id,
        branch_id=payload.branch_id,
        office_id=payload.office_id,
        from_date=payload.from_date,
        to_date=payload.to_date,
    )
    return SingleResponse(data=data)


@router.post(
    "/check-slot",
    response_model=SingleResponse[CheckSlotResponse],
    dependencies=[Depends(RequirePermission("AVAILABILITY_READ"))],
)
async def check_slot(payload: CheckSlotRequest, db: DBSession) -> SingleResponse[CheckSlotResponse]:
    data = await availability_service.check_slot(
        db,
        doctor_id=payload.doctor_id,
        office_id=payload.office_id,
        product_id=payload.product_id,
        scheduled_for=payload.scheduled_for,
    )
    return SingleResponse(data=data)
