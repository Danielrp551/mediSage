"""
Repositorio del historial inmutable de estados de lead. `list_for_person` devuelve
la traza completa de una persona, más reciente primero (no se filtra por active —
es audit trail honesto, aunque se conserva la columna `active` por el mixin).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.crm.models.lead_status_history import LeadStatusHistory
from app.shared.base_repository import BaseRepository


class LeadStatusHistoryRepository(BaseRepository[LeadStatusHistory]):
    ALLOWED_FIELDS: set[str] = set()

    def __init__(self) -> None:
        super().__init__(LeadStatusHistory)

    async def list_for_person(self, db: AsyncSession, person_id: str) -> list[LeadStatusHistory]:
        result = await db.execute(
            select(LeadStatusHistory)
            .where(LeadStatusHistory.person_id == person_id)
            .order_by(LeadStatusHistory.changed_at.desc())
        )
        return list(result.scalars().all())


lead_status_history_repository = LeadStatusHistoryRepository()
