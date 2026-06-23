"""
Lectura informativa on-demand (Fase 2). Resuelve los CalendarSource HABILITADOS de la sede
(branch_id == X OR NULL), agrupa por conexión, refresca el token si expiró (reusa
`connection.resolve_creds`), llama `list_events` por calendario y aplana a ExternalEventItem.

AISLAMIENTO (regla §23, contrato NO-negociable): cada conexión se intenta dentro de un try;
un fallo (token revocado, provider caído, secreto faltante) marca `sources_health` y NO
contamina al resto. El endpoint SIEMPRE devuelve 200 con lo que pudo leer + la salud — un
calendario externo caído NO puede romper la grilla ni la reserva (la capa es aditiva).

A diferencia de `list_external_calendars` (config, que PROPAGA el 400), aquí los codes
(`CALENDAR_TOKEN_REFRESH_FAILED`/`CALENDAR_CREDENTIALS_MISSING`/`CALENDAR_READ_FAILED`) viajan
dentro de `sources_health[].error`, nunca como un 4xx/5xx.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.calendar.enums import ConnectionStatus
from app.modules.calendar.models.calendar_source import CalendarSource
from app.modules.calendar.repositories.calendar_source import (
    calendar_source_repository,
)
from app.modules.calendar.schemas.external_event import (
    ExternalEventItem,
    ExternalEventsResponse,
    SourceHealth,
)
from app.modules.calendar.services.connection import resolve_creds
from app.modules.calendar.services.providers import get_adapter
from app.modules.clinic.repositories.branch import branch_repository
from app.shared.base_schemas import SingleResponse
from app.shared.utils import utc_now


async def _branch_name_map(db: AsyncSession, branch_ids: list[str | None]) -> dict[str, str]:
    """Denorm batch de branch_id → branch.name (clinic). Solo ids no-NULL."""
    ids = [bid for bid in branch_ids if bid]
    if not ids:
        return {}
    branches = await branch_repository.get_by_ids(db, list(set(ids)))
    return {b.id: b.name for b in branches}


async def read_external_events(
    db: AsyncSession, *, branch_id: str, time_min: datetime, time_max: datetime
) -> SingleResponse[ExternalEventsResponse]:
    sources = await calendar_source_repository.list_enabled_for_branch(db, branch_id)
    branch_names = await _branch_name_map(db, [s.branch_id for s in sources])

    # Un refresh + N list_events por conexión (no por calendario): agrupar por conexión.
    by_connection: dict[str, list[CalendarSource]] = defaultdict(list)
    for src in sources:
        by_connection[src.connection_id].append(src)

    events: list[ExternalEventItem] = []
    health: list[SourceHealth] = []
    for conn_sources in by_connection.values():
        conn = conn_sources[0].connection  # eager-loaded (selectinload) — lazy='raise'
        if conn is None or not conn.active:
            continue  # conexión en pausa manual → no se lee
        try:
            # get_adapter DENTRO del try: un provider corrupto (varchar libre) → viaja en
            # sources_health, NO un 4xx que aborte todo el overlay (§23: aislamiento por conexión).
            adapter = get_adapter(conn.provider)
            creds = await resolve_creds(db, conn, adapter)
            for src in conn_sources:
                ext = await adapter.list_events(
                    creds,
                    calendar_id=src.external_calendar_id,
                    time_min=time_min,
                    time_max=time_max,
                )
                events.extend(
                    ExternalEventItem(
                        external_id=e.external_id,
                        title=e.title,
                        starts_at=e.starts_at,
                        ends_at=e.ends_at,
                        all_day=e.all_day,
                        branch_id=src.branch_id,
                        branch_name=branch_names.get(src.branch_id) if src.branch_id else None,
                        source_id=src.id,
                    )
                    for e in ext
                )
            # Una lectura OK CURA un status degradado (needs_reauth/error) de un fallo transitorio
            # previo → la barra de salud y la lista de conexiones reflejan el resultado REAL del
            # intento, no un status pegado hasta una reconexión manual.
            conn.status = ConnectionStatus.connected.value
            conn.last_checked_at = utc_now()
            conn.last_error = None
            health.append(SourceHealth(connection_id=conn.id, status=ConnectionStatus.connected))
        except Exception as exc:  # noqa: BLE001 — AISLAMIENTO §23: marcar salud y SEGUIR
            conn.last_error = str(exc)[:500]
            code = getattr(exc, "code", None) or "CALENDAR_READ_FAILED"
            # El resolver de secretos es compartido con conversations → re-mapear su code genérico
            # al de calendar (el usuario ve este code en el tooltip del overlay de CALENDARIO).
            if code == "CHANNEL_CREDENTIALS_MISSING":
                code = "CALENDAR_CREDENTIALS_MISSING"
            health.append(
                SourceHealth(
                    connection_id=conn.id,
                    status=ConnectionStatus(conn.status),
                    error=code,
                )
            )
    return SingleResponse(data=ExternalEventsResponse(events=events, sources_health=health))
