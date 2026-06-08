"""
Repositorio del timeline de estado de una cita (append-only). Sin SoftDelete (el
modelo no tiene deleted_at) → NO usar get_by_id/get_paginated heredados; solo
`list_for_appointment` (ordenado por changed_at asc). Espeja crm.lead_status_history.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.scheduling.models.appointment_status_history import (
    AppointmentStatusHistory,
)
from app.shared.base_repository import BaseRepository


class AppointmentStatusHistoryRepository(BaseRepository[AppointmentStatusHistory]):
    ALLOWED_FIELDS: set[str] = set()

    def __init__(self) -> None:
        super().__init__(AppointmentStatusHistory)

    async def list_for_appointment(
        self, db: AsyncSession, appointment_id: str
    ) -> list[AppointmentStatusHistory]:
        result = await db.execute(
            select(AppointmentStatusHistory)
            .where(
                AppointmentStatusHistory.appointment_id == appointment_id,
                AppointmentStatusHistory.active.is_(True),
            )
            .order_by(AppointmentStatusHistory.changed_at.asc())
        )
        return list(result.scalars().all())


appointment_status_history_repository = AppointmentStatusHistoryRepository()
