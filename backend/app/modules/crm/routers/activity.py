"""
Router del timeline (LeadActivity). Lectura del feed (POST
/persons/{id}/activities/list, LEAD_ACTIVITIES_READ) + el COMPOSER del asesor (F5):
POST crear / PUT editar / DELETE borrar (active=false), todos LEAD_ACTIVITIES_WRITE.
Solo se pueden crear los ADVISOR_ACTIVITY_TYPES (NOTE/CALL_ATTEMPT/FOLLOW_UP_*) — el
schema lo valida (422). `/activities/list` se declara antes de `/activities/{act_id}`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from app.core.dependencies import CurrentAuth, DBSession, RequirePermission
from app.modules.crm.schemas.activity import (
    ActivityCreate,
    ActivityItem,
    ActivityListRequest,
    ActivityUpdate,
)
from app.modules.crm.services import lead_activity as lead_activity_service
from app.shared.base_schemas import SingleResponse

router = APIRouter(prefix="/persons", tags=["crm · activity"])

PersonIdPath = Annotated[str, Path(min_length=1, description="Person UUID")]
ActivityIdPath = Annotated[str, Path(min_length=1, description="LeadActivity UUID")]


@router.post(
    "/{person_id}/activities/list",
    response_model=SingleResponse[list[ActivityItem]],
    dependencies=[Depends(RequirePermission("LEAD_ACTIVITIES_READ"))],
)
async def list_activities(
    person_id: PersonIdPath, payload: ActivityListRequest, db: DBSession
) -> SingleResponse[list[ActivityItem]]:
    return await lead_activity_service.list_for_person(db, person_id, payload)


@router.post(
    "/{person_id}/activities",
    response_model=SingleResponse[ActivityItem],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RequirePermission("LEAD_ACTIVITIES_WRITE"))],
)
async def create_activity(
    person_id: PersonIdPath, payload: ActivityCreate, db: DBSession, actor: CurrentAuth
) -> SingleResponse[ActivityItem]:
    return await lead_activity_service.create(db, person_id, payload, actor_id=actor.id)


@router.put(
    "/{person_id}/activities/{activity_id}",
    response_model=SingleResponse[ActivityItem],
    dependencies=[Depends(RequirePermission("LEAD_ACTIVITIES_WRITE"))],
)
async def update_activity(
    person_id: PersonIdPath,
    activity_id: ActivityIdPath,
    payload: ActivityUpdate,
    db: DBSession,
    actor: CurrentAuth,
) -> SingleResponse[ActivityItem]:
    return await lead_activity_service.update(
        db, person_id, activity_id, payload, actor_id=actor.id
    )


@router.delete(
    "/{person_id}/activities/{activity_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(RequirePermission("LEAD_ACTIVITIES_WRITE"))],
)
async def delete_activity(
    person_id: PersonIdPath, activity_id: ActivityIdPath, db: DBSession, actor: CurrentAuth
) -> None:
    await lead_activity_service.delete(db, person_id, activity_id, actor_id=actor.id)
