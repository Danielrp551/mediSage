"""
Repositorio de `CalendarConnection`. `ALLOWED_FIELDS` = whitelist estricta de columnas
REALES filtrable/ordenable desde el frontend (los denorm como sources_count NO van —
lección cd10c78). `BaseRepository` filtra `deleted_at IS NULL` en cada read.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, with_loader_criteria

from app.modules.calendar.models.calendar_connection import CalendarConnection
from app.modules.calendar.models.calendar_source import CalendarSource
from app.shared.base_repository import BaseRepository


class CalendarConnectionRepository(BaseRepository[CalendarConnection]):
    # Solo columnas reales. provider/account_email/status/active son filtrables; los denorm
    # (sources_count) NO.
    ALLOWED_FIELDS: set[str] = {
        "provider",
        "account_email",
        "status",
        "active",
        "created_on",
        "updated_on",
    }

    def __init__(self) -> None:
        super().__init__(CalendarConnection)

    async def get_by_provider_email(
        self, db: AsyncSession, provider: str, account_email: str
    ) -> CalendarConnection | None:
        """Guard de UNIQUE PARCIAL (CALENDAR_CONNECTION_ALREADY_EXISTS). Solo vivas."""
        result = await db.execute(
            select(CalendarConnection).where(
                CalendarConnection.provider == provider,
                CalendarConnection.account_email == account_email,
                CalendarConnection.deleted_at.is_(None),
            )
        )
        return result.scalars().first()

    async def get_full(self, db: AsyncSession, connection_id: str) -> CalendarConnection | None:
        """Detalle: carga los sources VIVOS (la relación es lazy='raise'). `with_loader_criteria`
        filtra los soft-deleteados EN la query (molde clinic Office.get_full) — NO se asigna a
        `conn.sources` en memoria (mutaría la relación). `populate_existing=True` FUERZA recargar
        la colección aunque el objeto ya esté en el identity map con sources cacheados (p.ej. el
        reload-via-get_full de replace_sources, en la misma tx): sin esto, selectinload no
        repuebla una colección ya cargada y devuelve datos stale."""
        result = await db.execute(
            select(CalendarConnection)
            .where(
                CalendarConnection.id == connection_id,
                CalendarConnection.deleted_at.is_(None),
            )
            .options(
                selectinload(CalendarConnection.sources),
                with_loader_criteria(CalendarSource, CalendarSource.deleted_at.is_(None)),
            )
            .execution_options(populate_existing=True)
        )
        return result.scalars().first()

    async def sources_count_map(
        self, db: AsyncSession, connection_ids: list[str]
    ) -> dict[str, int]:
        """Batch (sin N+1) para denormalizar sources_count en la lista de conexiones."""
        if not connection_ids:
            return {}
        result = await db.execute(
            select(CalendarSource.connection_id, func.count())
            .where(
                CalendarSource.connection_id.in_(connection_ids),
                CalendarSource.deleted_at.is_(None),
            )
            .group_by(CalendarSource.connection_id)
        )
        return {row[0]: row[1] for row in result.all()}


calendar_connection_repository = CalendarConnectionRepository()
