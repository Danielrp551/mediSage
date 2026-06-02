"""
Router del ciclo de vida del hilo lead de una Person: estado actual, crear lead,
transicionar (matriz F2), el historial y `promote-to-customer` (F4 — promueve el lead
a cliente, cerrándolo como ganado si la matriz lo permite). Permisos: leer estado =
PERSONS_READ; crear/transicionar/promover = LEAD_ACTIVITIES_WRITE; historial =
LEAD_STATUS_HISTORY_READ.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from app.core.dependencies import CurrentAuth, DBSession, RequirePermission
from app.modules.crm.schemas.customer_lifecycle import (
    PersonCustomerStatusDetail,
    PromoteToCustomerRequest,
)
from app.modules.crm.schemas.lead_lifecycle import (
    LeadStatusCreateRequest,
    LeadStatusHistoryItem,
    LeadStatusTransitionRequest,
    PersonLeadStatusDetail,
)
from app.modules.crm.services import person_customer_status as person_customer_status_service
from app.modules.crm.services import person_lead_status as person_lead_status_service
from app.shared.base_schemas import SingleResponse

router = APIRouter(prefix="/persons", tags=["crm · lead lifecycle"])

PersonIdPath = Annotated[str, Path(min_length=1, description="Person UUID")]


@router.get(
    "/{person_id}/lead-status",
    response_model=SingleResponse[PersonLeadStatusDetail | None],
    dependencies=[Depends(RequirePermission("PERSONS_READ"))],
)
async def get_lead_status(
    person_id: PersonIdPath, db: DBSession
) -> SingleResponse[PersonLeadStatusDetail | None]:
    return await person_lead_status_service.get_current(db, person_id)


@router.post(
    "/{person_id}/lead-status",
    response_model=SingleResponse[PersonLeadStatusDetail],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RequirePermission("LEAD_ACTIVITIES_WRITE"))],
)
async def create_lead_status(
    person_id: PersonIdPath,
    payload: LeadStatusCreateRequest,
    db: DBSession,
    actor: CurrentAuth,
) -> SingleResponse[PersonLeadStatusDetail]:
    return await person_lead_status_service.create(db, person_id, payload, actor_id=actor.id)


@router.post(
    "/{person_id}/lead-status/transition",
    response_model=SingleResponse[PersonLeadStatusDetail | None],
    dependencies=[Depends(RequirePermission("LEAD_ACTIVITIES_WRITE"))],
)
async def transition_lead_status(
    person_id: PersonIdPath,
    payload: LeadStatusTransitionRequest,
    db: DBSession,
    actor: CurrentAuth,
) -> SingleResponse[PersonLeadStatusDetail | None]:
    return await person_lead_status_service.transition(
        db, person_id, payload.to_lead_status_id, actor_id=actor.id, reason=payload.reason
    )


@router.get(
    "/{person_id}/lead-status/history",
    response_model=SingleResponse[list[LeadStatusHistoryItem]],
    dependencies=[Depends(RequirePermission("LEAD_STATUS_HISTORY_READ"))],
)
async def get_lead_status_history(
    person_id: PersonIdPath, db: DBSession
) -> SingleResponse[list[LeadStatusHistoryItem]]:
    return await person_lead_status_service.get_history(db, person_id)


@router.post(
    "/{person_id}/promote-to-customer",
    response_model=SingleResponse[PersonCustomerStatusDetail],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RequirePermission("LEAD_ACTIVITIES_WRITE"))],
)
async def promote_to_customer(
    person_id: PersonIdPath,
    payload: PromoteToCustomerRequest,
    db: DBSession,
    actor: CurrentAuth,
) -> SingleResponse[PersonCustomerStatusDetail]:
    return await person_customer_status_service.promote_from_lead(
        db, person_id, actor_id=actor.id, reason=payload.reason
    )
