"""
OfficeOperatingHours endpoints, nested under /offices/{office_id}/operating-hours.
GET lists the weekly pattern; PUT replaces it atomically (bulk). `PUT` is the
correct verb here — it is an idempotent replacement of the whole collection, the
one intentional exception to the module's "PUT for full updates, no per-row
collection CRUD" convention. Permission gating via `dependencies=[...]`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path

from app.core.dependencies import CurrentAuth, DBSession, RequirePermission
from app.modules.clinic.schemas.office_operating_hours import (
    OfficeOperatingHoursItem,
    OfficeOperatingHoursReplace,
)
from app.modules.clinic.services import office_operating_hours as hours_service
from app.shared.base_schemas import SingleResponse

router = APIRouter(prefix="/offices", tags=["clinic · office hours"])


OfficeIdPath = Annotated[str, Path(min_length=1, description="Office UUID")]


@router.get(
    "/{office_id}/operating-hours",
    response_model=SingleResponse[list[OfficeOperatingHoursItem]],
    dependencies=[Depends(RequirePermission("OFFICE_HOURS_READ"))],
)
async def get_operating_hours(
    office_id: OfficeIdPath, db: DBSession
) -> SingleResponse[list[OfficeOperatingHoursItem]]:
    return await hours_service.list_for_office(db, office_id)


@router.put(
    "/{office_id}/operating-hours",
    response_model=SingleResponse[list[OfficeOperatingHoursItem]],
    dependencies=[Depends(RequirePermission("OFFICE_HOURS_WRITE"))],
)
async def replace_operating_hours(
    office_id: OfficeIdPath,
    payload: OfficeOperatingHoursReplace,
    db: DBSession,
    actor: CurrentAuth,
) -> SingleResponse[list[OfficeOperatingHoursItem]]:
    return await hours_service.replace(db, office_id, payload, actor_id=actor.id)
