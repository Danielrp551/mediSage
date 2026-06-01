"""
Router del catálogo CustomerStatus (+ matriz). Análogo a lead_status SIN is_won.
Permisos: CUSTOMER_STATUSES_READ / CUSTOMER_STATUSES_WRITE.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from app.core.dependencies import CurrentAuth, DBSession, RequirePermission
from app.modules.crm.schemas.customer_status import (
    CustomerStatusCreate,
    CustomerStatusItem,
    CustomerStatusOption,
    CustomerStatusUpdate,
    CustomerTransitionTargets,
)
from app.modules.crm.schemas.lead_status import StatusTransitionUpdate
from app.modules.crm.services import customer_status as customer_status_service
from app.shared.base_schemas import PaginatedResponse, QueryRequest, SingleResponse

router = APIRouter(prefix="/customer-statuses", tags=["crm · customer statuses"])

StatusIdPath = Annotated[str, Path(min_length=1, description="CustomerStatus UUID")]


@router.get(
    "/active",
    response_model=list[CustomerStatusOption],
    dependencies=[Depends(RequirePermission("CUSTOMER_STATUSES_READ"))],
)
async def list_active_customer_statuses(db: DBSession) -> list[CustomerStatusOption]:
    return await customer_status_service.list_active(db)


@router.post(
    "/list",
    response_model=PaginatedResponse[CustomerStatusItem],
    dependencies=[Depends(RequirePermission("CUSTOMER_STATUSES_READ"))],
)
async def list_customer_statuses(
    query: QueryRequest, db: DBSession
) -> PaginatedResponse[CustomerStatusItem]:
    return await customer_status_service.list_paginated(db, query)


@router.post(
    "",
    response_model=SingleResponse[CustomerStatusItem],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RequirePermission("CUSTOMER_STATUSES_WRITE"))],
)
async def create_customer_status(
    payload: CustomerStatusCreate, db: DBSession, actor: CurrentAuth
) -> SingleResponse[CustomerStatusItem]:
    return await customer_status_service.create(db, payload, actor_id=actor.id)


@router.put(
    "/{status_id}",
    response_model=SingleResponse[CustomerStatusItem],
    dependencies=[Depends(RequirePermission("CUSTOMER_STATUSES_WRITE"))],
)
async def update_customer_status(
    status_id: StatusIdPath, payload: CustomerStatusUpdate, db: DBSession, actor: CurrentAuth
) -> SingleResponse[CustomerStatusItem]:
    return await customer_status_service.update(db, status_id, payload, actor_id=actor.id)


@router.delete(
    "/{status_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(RequirePermission("CUSTOMER_STATUSES_WRITE"))],
)
async def delete_customer_status(
    status_id: StatusIdPath, db: DBSession, actor: CurrentAuth
) -> None:
    await customer_status_service.remove(db, status_id, actor_id=actor.id)


@router.get(
    "/{status_id}/transitions",
    response_model=SingleResponse[CustomerTransitionTargets],
    dependencies=[Depends(RequirePermission("CUSTOMER_STATUSES_READ"))],
)
async def get_customer_status_transitions(
    status_id: StatusIdPath, db: DBSession
) -> SingleResponse[CustomerTransitionTargets]:
    return await customer_status_service.get_transitions(db, status_id)


@router.put(
    "/{status_id}/transitions",
    response_model=SingleResponse[CustomerTransitionTargets],
    dependencies=[Depends(RequirePermission("CUSTOMER_STATUSES_WRITE"))],
)
async def set_customer_status_transitions(
    status_id: StatusIdPath,
    payload: StatusTransitionUpdate,
    db: DBSession,
    actor: CurrentAuth,
) -> SingleResponse[CustomerTransitionTargets]:
    return await customer_status_service.set_transitions(db, status_id, payload, actor_id=actor.id)
