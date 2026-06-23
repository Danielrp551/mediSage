"""
Router del overlay informativo (F2). `GET /external-events?branch_id&from&to` →
`SingleResponse[ExternalEventsResponse]`, gated CALENDAR_EXTERNAL_EVENTS_READ. best-effort:
SIEMPRE 200 (una conexión caída viaja en `sources_health`, nunca un 5xx — regla §23).

⚠ `from` es palabra reservada en Python → `from_` con `Query(alias="from")` (la URL usa
`?from=`). Es una ruta ESTÁTICA bajo `/calendar` → va ANTES de `/connections/{id}` (no la
captura la paramétrica; misma regla que scheduling).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import DBSession, RequirePermission
from app.modules.calendar.schemas.external_event import ExternalEventsResponse
from app.modules.calendar.services import external_read
from app.shared.base_schemas import SingleResponse

router = APIRouter(tags=["calendar · events"])


@router.get(
    "/external-events",
    response_model=SingleResponse[ExternalEventsResponse],
    dependencies=[Depends(RequirePermission("CALENDAR_EXTERNAL_EVENTS_READ"))],
)
async def external_events(
    db: DBSession,
    branch_id: Annotated[str, Query()],
    from_: Annotated[datetime, Query(alias="from")],
    to: Annotated[datetime, Query()],
) -> SingleResponse[ExternalEventsResponse]:
    return await external_read.read_external_events(
        db, branch_id=branch_id, time_min=from_, time_max=to
    )
