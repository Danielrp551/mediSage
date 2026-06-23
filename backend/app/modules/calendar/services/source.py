"""
Service de sources (módulo de funciones). `replace_sources` = bulk REPLACE atómico
(patrón clinic.OfficeOperatingHours): soft-delete los viejos + insert el set nuevo, en la
MISMA tx del request. Valida cada branch_id no-NULL ANTES de insertar (404 BRANCH_NOT_FOUND,
lección §20/§22 — todo FK real que el payload traiga se valida, no un 500 por el constraint).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.modules.calendar.models.calendar_source import CalendarSource
from app.modules.calendar.repositories.calendar_connection import (
    calendar_connection_repository,
)
from app.modules.calendar.repositories.calendar_source import (
    calendar_source_repository,
)
from app.modules.calendar.schemas.connection import CalendarConnectionDetail
from app.modules.calendar.schemas.source import CalendarSourcesReplace
from app.modules.calendar.services.connection import get_connection
from app.modules.clinic.repositories.branch import branch_repository
from app.shared.base_schemas import SingleResponse
from app.shared.utils import generate_uuid, utc_now


async def replace_sources(
    db: AsyncSession,
    connection_id: str,
    payload: CalendarSourcesReplace,
    *,
    actor_id: str,
) -> SingleResponse[CalendarConnectionDetail]:
    """Bulk REPLACE atómico: soft-delete los viejos + insert el set nuevo. Valida cada
    branch_id ANTES de insertar (404 BRANCH_NOT_FOUND). El replace es atómico por la tx del
    request (get_db commitea al final): si el insert lanza (p.ej. un duplicado de external_
    calendar_id en el payload), rollback y el mapeo viejo queda intacto."""
    conn = await calendar_connection_repository.get_full(db, connection_id)
    if conn is None:
        raise NotFoundException("Conexión no encontrada", code="CALENDAR_CONNECTION_NOT_FOUND")

    # 1) Validar branch_ids (los no-NULL) contra clinic.branch VIVO (un get_by_ids batch).
    branch_ids = [s.branch_id for s in payload.sources if s.branch_id is not None]
    if branch_ids:
        existing = await branch_repository.get_by_ids(db, list(set(branch_ids)))
        existing_ids = {b.id for b in existing}
        for bid in branch_ids:
            if bid not in existing_ids:
                raise NotFoundException(f"Sede {bid} no encontrada", code="BRANCH_NOT_FOUND")

    # 2) Soft-delete los sources viejos + insert el set nuevo (misma tx → atómico).
    await calendar_source_repository.soft_delete_for_connection(db, connection_id)
    now = utc_now()
    for s in payload.sources:
        db.add(
            CalendarSource(
                id=generate_uuid(),
                connection_id=connection_id,
                external_calendar_id=s.external_calendar_id,
                external_calendar_name=s.external_calendar_name,
                branch_id=s.branch_id,
                active=s.is_enabled,  # is_enabled → ActiveMixin.active
                created_by=actor_id,
                created_on=now,
                updated_by=actor_id,
                updated_on=now,
            )
        )
    await db.flush()
    return await get_connection(db, connection_id)  # reload-via-get (relación lazy='raise')
