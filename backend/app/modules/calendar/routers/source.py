"""
Router del bulk-replace de sources. `PUT /connections/{id}/sources` (no PATCH). Es un sufijo
literal tras `/{id}` → no colisiona con `GET /connections/{id}`. CALENDAR_CONNECTIONS_WRITE.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path

from app.core.dependencies import CurrentAuth, DBSession, RequirePermission
from app.modules.calendar.schemas.connection import CalendarConnectionDetail
from app.modules.calendar.schemas.source import CalendarSourcesReplace
from app.modules.calendar.services import source as source_service
from app.shared.base_schemas import SingleResponse

router = APIRouter(prefix="/connections", tags=["calendar · sources"])

ConnIdPath = Annotated[str, Path(min_length=1, description="Connection UUID")]


@router.put(
    "/{connection_id}/sources",
    response_model=SingleResponse[CalendarConnectionDetail],
    dependencies=[Depends(RequirePermission("CALENDAR_CONNECTIONS_WRITE"))],
)
async def replace_sources(
    connection_id: ConnIdPath,
    payload: CalendarSourcesReplace,
    db: DBSession,
    actor: CurrentAuth,
) -> SingleResponse[CalendarConnectionDetail]:
    return await source_service.replace_sources(db, connection_id, payload, actor_id=actor.id)
