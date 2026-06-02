"""
Routers de asignación de owner + asesores + bandeja del asesor. Tres APIRouter:
- `router` (/persons/{id}/assignment[/auto]) — get / reassign manual / round-robin auto.
- `advisors_router` (/advisors/active) — dropdown de asesores (crm-owned, ver backend.md).
- `me_router` (/me/leads/list) — los leads del asesor logueado (resuelto de CurrentAuth).
Permisos: LEAD_ASSIGNMENTS_READ (lectura) / LEAD_ASSIGNMENTS_WRITE (reasignar/auto) /
MY_LEADS_READ (mis leads).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path

from app.core.dependencies import CurrentAuth, DBSession, RequirePermission
from app.modules.crm.schemas.assignment import (
    AdvisorOption,
    AssignmentRequest,
    LeadAssignmentDetail,
    MyLeadItem,
)
from app.modules.crm.services import lead_assignment as lead_assignment_service
from app.shared.base_schemas import PaginatedResponse, QueryRequest, SingleResponse

router = APIRouter(prefix="/persons", tags=["crm · assignment"])
advisors_router = APIRouter(prefix="/advisors", tags=["crm · assignment"])
me_router = APIRouter(prefix="/me", tags=["crm · me"])

PersonIdPath = Annotated[str, Path(min_length=1, description="Person UUID")]


@router.get(
    "/{person_id}/assignment",
    response_model=SingleResponse[LeadAssignmentDetail],
    dependencies=[Depends(RequirePermission("LEAD_ASSIGNMENTS_READ"))],
)
async def get_assignment(
    person_id: PersonIdPath, db: DBSession
) -> SingleResponse[LeadAssignmentDetail]:
    return await lead_assignment_service.get_current(db, person_id)


@router.put(
    "/{person_id}/assignment",
    response_model=SingleResponse[LeadAssignmentDetail],
    dependencies=[Depends(RequirePermission("LEAD_ASSIGNMENTS_WRITE"))],
)
async def put_assignment(
    person_id: PersonIdPath, payload: AssignmentRequest, db: DBSession, actor: CurrentAuth
) -> SingleResponse[LeadAssignmentDetail]:
    return await lead_assignment_service.reassign(
        db, person_id, payload.advisor_user_id, actor_id=actor.id, reason=payload.reason
    )


@router.post(
    "/{person_id}/assignment/auto",
    response_model=SingleResponse[LeadAssignmentDetail],
    dependencies=[Depends(RequirePermission("LEAD_ASSIGNMENTS_WRITE"))],
)
async def auto_assign(
    person_id: PersonIdPath, db: DBSession, actor: CurrentAuth
) -> SingleResponse[LeadAssignmentDetail]:
    return await lead_assignment_service.assign_round_robin(db, person_id, actor_id=actor.id)


@advisors_router.get(
    "/active",
    response_model=list[AdvisorOption],
    dependencies=[Depends(RequirePermission("LEAD_ASSIGNMENTS_READ"))],
)
async def list_active_advisors(db: DBSession) -> list[AdvisorOption]:
    return await lead_assignment_service.list_advisors(db)


@me_router.post(
    "/leads/list",
    response_model=PaginatedResponse[MyLeadItem],
    dependencies=[Depends(RequirePermission("MY_LEADS_READ"))],
)
async def list_my_leads(
    query: QueryRequest, db: DBSession, auth: CurrentAuth
) -> PaginatedResponse[MyLeadItem]:
    return await lead_assignment_service.list_my_leads(db, auth.id, query)
