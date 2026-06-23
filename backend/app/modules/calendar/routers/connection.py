"""
Routers de conexiones. Permiso vía dependencies=[Depends(RequirePermission(...))]; actor:
CurrentAuth aparte cuando se necesita el id. Rutas estáticas (`/list`) antes de `/{id}`.
CALENDAR_CONNECTIONS_WRITE cubre disconnect + el live `/calendars` (config).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from app.core.dependencies import CurrentAuth, DBSession, RequirePermission
from app.modules.calendar.schemas.connection import (
    CalendarConnectionDetail,
    CalendarConnectionItem,
)
from app.modules.calendar.schemas.source import ExternalCalendarOption
from app.modules.calendar.services import connection as connection_service
from app.shared.base_schemas import (
    PaginatedResponse,
    QueryRequest,
    SingleResponse,
)

router = APIRouter(prefix="/connections", tags=["calendar · connections"])

ConnIdPath = Annotated[str, Path(min_length=1, description="Connection UUID")]


@router.post(
    "/list",
    response_model=PaginatedResponse[CalendarConnectionItem],
    dependencies=[Depends(RequirePermission("CALENDAR_CONNECTIONS_READ"))],
)
async def list_connections(
    query: QueryRequest, db: DBSession
) -> PaginatedResponse[CalendarConnectionItem]:
    return await connection_service.list_connections(db, query)


@router.get(
    "/{connection_id}",
    response_model=SingleResponse[CalendarConnectionDetail],
    dependencies=[Depends(RequirePermission("CALENDAR_CONNECTIONS_READ"))],
)
async def get_connection(
    connection_id: ConnIdPath, db: DBSession
) -> SingleResponse[CalendarConnectionDetail]:
    return await connection_service.get_connection(db, connection_id)


@router.delete(
    "/{connection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(RequirePermission("CALENDAR_CONNECTIONS_WRITE"))],
)
async def disconnect(connection_id: ConnIdPath, db: DBSession, actor: CurrentAuth) -> None:
    await connection_service.disconnect(db, connection_id, actor_id=actor.id)


@router.get(
    "/{connection_id}/calendars",
    response_model=SingleResponse[list[ExternalCalendarOption]],
    dependencies=[Depends(RequirePermission("CALENDAR_CONNECTIONS_WRITE"))],
)
async def list_external_calendars(
    connection_id: ConnIdPath, db: DBSession
) -> SingleResponse[list[ExternalCalendarOption]]:
    return await connection_service.list_external_calendars(db, connection_id)
