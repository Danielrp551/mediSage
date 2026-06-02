"""
Router del timeline (LeadActivity). En F3 expone solo la LECTURA del feed
(POST /persons/{id}/activities/list) que alimenta el tab Actividad (Iteración A,
read-only: muestra STATUS_CHANGE/REASSIGNED). El composer del asesor
(POST/PUT/DELETE) llega en F5. Permiso: LEAD_ACTIVITIES_READ.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path

from app.core.dependencies import DBSession, RequirePermission
from app.modules.crm.schemas.activity import ActivityItem, ActivityListRequest
from app.modules.crm.services import lead_activity as lead_activity_service
from app.shared.base_schemas import SingleResponse

router = APIRouter(prefix="/persons", tags=["crm · activity"])

PersonIdPath = Annotated[str, Path(min_length=1, description="Person UUID")]


@router.post(
    "/{person_id}/activities/list",
    response_model=SingleResponse[list[ActivityItem]],
    dependencies=[Depends(RequirePermission("LEAD_ACTIVITIES_READ"))],
)
async def list_activities(
    person_id: PersonIdPath, payload: ActivityListRequest, db: DBSession
) -> SingleResponse[list[ActivityItem]]:
    return await lead_activity_service.list_for_person(db, person_id, payload)
