"""
Router del catálogo LeadStatus (+ matriz de transiciones). `/active` antes de las
rutas dinámicas. Permisos: LEAD_STATUSES_READ (lectura) / LEAD_STATUSES_WRITE
(CRUD + editar la matriz). El service devuelve los envelopes; `/active` devuelve
lista cruda (sin envelope), consistente con el resto del módulo.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from app.core.dependencies import CurrentAuth, DBSession, RequirePermission
from app.modules.crm.schemas.lead_status import (
    LeadStatusCreate,
    LeadStatusItem,
    LeadStatusOption,
    LeadStatusUpdate,
    StatusTransitionUpdate,
    TransitionTargets,
)
from app.modules.crm.services import lead_status as lead_status_service
from app.shared.base_schemas import PaginatedResponse, QueryRequest, SingleResponse

router = APIRouter(prefix="/lead-statuses", tags=["crm · lead statuses"])

StatusIdPath = Annotated[str, Path(min_length=1, description="LeadStatus UUID")]


@router.get(
    "/active",
    response_model=list[LeadStatusOption],
    dependencies=[Depends(RequirePermission("LEAD_STATUSES_READ"))],
)
async def list_active_lead_statuses(db: DBSession) -> list[LeadStatusOption]:
    return await lead_status_service.list_active(db)


@router.post(
    "/list",
    response_model=PaginatedResponse[LeadStatusItem],
    dependencies=[Depends(RequirePermission("LEAD_STATUSES_READ"))],
)
async def list_lead_statuses(
    query: QueryRequest, db: DBSession
) -> PaginatedResponse[LeadStatusItem]:
    return await lead_status_service.list_paginated(db, query)


@router.post(
    "",
    response_model=SingleResponse[LeadStatusItem],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RequirePermission("LEAD_STATUSES_WRITE"))],
)
async def create_lead_status(
    payload: LeadStatusCreate, db: DBSession, actor: CurrentAuth
) -> SingleResponse[LeadStatusItem]:
    return await lead_status_service.create(db, payload, actor_id=actor.id)


@router.put(
    "/{status_id}",
    response_model=SingleResponse[LeadStatusItem],
    dependencies=[Depends(RequirePermission("LEAD_STATUSES_WRITE"))],
)
async def update_lead_status(
    status_id: StatusIdPath, payload: LeadStatusUpdate, db: DBSession, actor: CurrentAuth
) -> SingleResponse[LeadStatusItem]:
    return await lead_status_service.update(db, status_id, payload, actor_id=actor.id)


@router.delete(
    "/{status_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(RequirePermission("LEAD_STATUSES_WRITE"))],
)
async def delete_lead_status(status_id: StatusIdPath, db: DBSession, actor: CurrentAuth) -> None:
    await lead_status_service.remove(db, status_id, actor_id=actor.id)


@router.get(
    "/{status_id}/transitions",
    response_model=SingleResponse[TransitionTargets],
    dependencies=[Depends(RequirePermission("LEAD_STATUSES_READ"))],
)
async def get_lead_status_transitions(
    status_id: StatusIdPath, db: DBSession
) -> SingleResponse[TransitionTargets]:
    return await lead_status_service.get_transitions(db, status_id)


@router.put(
    "/{status_id}/transitions",
    response_model=SingleResponse[TransitionTargets],
    dependencies=[Depends(RequirePermission("LEAD_STATUSES_WRITE"))],
)
async def set_lead_status_transitions(
    status_id: StatusIdPath,
    payload: StatusTransitionUpdate,
    db: DBSession,
    actor: CurrentAuth,
) -> SingleResponse[TransitionTargets]:
    return await lead_status_service.set_transitions(db, status_id, payload, actor_id=actor.id)
