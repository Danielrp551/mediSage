"""
Repositorio de `CalendarSource`. No hay `/list` de sources (se leen por conexión o por
sede), así que `ALLOWED_FIELDS` queda vacío. `BaseRepository` filtra `deleted_at IS NULL`.

`soft_delete_for_connection` es el paso 1 del bulk-replace atómico (soft-delete los viejos
+ insert el set nuevo, patrón clinic.OfficeOperatingHours.replace).
"""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.calendar.models.calendar_source import CalendarSource
from app.shared.base_repository import BaseRepository
from app.shared.utils import utc_now


class CalendarSourceRepository(BaseRepository[CalendarSource]):
    ALLOWED_FIELDS: set[str] = set()  # no hay /list de sources; se leen por connection/branch

    def __init__(self) -> None:
        super().__init__(CalendarSource)

    async def list_for_connection(
        self, db: AsyncSession, connection_id: str
    ) -> list[CalendarSource]:
        result = await db.execute(
            select(CalendarSource).where(
                CalendarSource.connection_id == connection_id,
                CalendarSource.deleted_at.is_(None),
            )
        )
        return list(result.scalars().all())

    async def soft_delete_for_connection(self, db: AsyncSession, connection_id: str) -> None:
        """Bulk-replace paso 1: soft-deletea los sources vivos de la conexión (el caller
        inserta el set nuevo con audit cols). NO usa DELETE real (mantiene la traza + libera
        el UNIQUE PARCIAL). Patrón clinic.OfficeOperatingHours.replace."""
        await db.execute(
            update(CalendarSource)
            .where(
                CalendarSource.connection_id == connection_id,
                CalendarSource.deleted_at.is_(None),
            )
            .values(deleted_at=utc_now())
        )


calendar_source_repository = CalendarSourceRepository()
