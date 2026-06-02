"""
Router del ciclo de vida del hilo cliente de una Person: estado actual, transicionar
(matriz customer F2) y el historial. El cliente NO se crea aquí (nace vía
`POST /persons/{id}/promote-to-customer`, en lead_lifecycle). Permisos: leer estado =
PERSONS_READ; transicionar = LEAD_ACTIVITIES_WRITE; historial = LEAD_STATUS_HISTORY_READ.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path

from app.core.dependencies import CurrentAuth, DBSession, RequirePermission
from app.modules.crm.schemas.customer_lifecycle import (
    CustomerStatusHistoryItem,
    CustomerStatusTransitionRequest,
    PersonCustomerStatusDetail,
)
from app.modules.crm.services import person_customer_status as person_customer_status_service
from app.shared.base_schemas import SingleResponse

router = APIRouter(prefix="/persons", tags=["crm · customer lifecycle"])

PersonIdPath = Annotated[str, Path(min_length=1, description="Person UUID")]


@router.get(
    "/{person_id}/customer-status",
    response_model=SingleResponse[PersonCustomerStatusDetail | None],
    dependencies=[Depends(RequirePermission("PERSONS_READ"))],
)
async def get_customer_status(
    person_id: PersonIdPath, db: DBSession
) -> SingleResponse[PersonCustomerStatusDetail | None]:
    return await person_customer_status_service.get_current(db, person_id)


@router.post(
    "/{person_id}/customer-status/transition",
    response_model=SingleResponse[PersonCustomerStatusDetail | None],
    dependencies=[Depends(RequirePermission("LEAD_ACTIVITIES_WRITE"))],
)
async def transition_customer_status(
    person_id: PersonIdPath,
    payload: CustomerStatusTransitionRequest,
    db: DBSession,
    actor: CurrentAuth,
) -> SingleResponse[PersonCustomerStatusDetail | None]:
    return await person_customer_status_service.transition(
        db, person_id, payload.to_customer_status_id, actor_id=actor.id, reason=payload.reason
    )


@router.get(
    "/{person_id}/customer-status/history",
    response_model=SingleResponse[list[CustomerStatusHistoryItem]],
    dependencies=[Depends(RequirePermission("LEAD_STATUS_HISTORY_READ"))],
)
async def get_customer_status_history(
    person_id: PersonIdPath, db: DBSession
) -> SingleResponse[list[CustomerStatusHistoryItem]]:
    return await person_customer_status_service.get_history(db, person_id)
