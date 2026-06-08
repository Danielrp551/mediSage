"""
Repositorio del log de cambios in-place de columnas no-estado de una cita
(append-only). Sin SoftDelete → solo `list_for_appointment` (ordenado por changed_at
asc). En F2 la tabla existe pero el WRITER (update) llega en F3 → list devuelve [].
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.scheduling.models.appointment_change_log import AppointmentChangeLog
from app.shared.base_repository import BaseRepository


class AppointmentChangeLogRepository(BaseRepository[AppointmentChangeLog]):
    ALLOWED_FIELDS: set[str] = set()

    def __init__(self) -> None:
        super().__init__(AppointmentChangeLog)

    async def list_for_appointment(
        self, db: AsyncSession, appointment_id: str
    ) -> list[AppointmentChangeLog]:
        result = await db.execute(
            select(AppointmentChangeLog)
            .where(
                AppointmentChangeLog.appointment_id == appointment_id,
                AppointmentChangeLog.active.is_(True),
            )
            .order_by(AppointmentChangeLog.changed_at.asc())
        )
        return list(result.scalars().all())


appointment_change_log_repository = AppointmentChangeLogRepository()
