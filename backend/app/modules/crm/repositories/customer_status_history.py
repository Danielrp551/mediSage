"""
Repositorio del historial inmutable de estados de cliente. `list_for_person`
devuelve la traza completa de una persona, más reciente primero (no se filtra por
active — es audit trail honesto). Análogo a `lead_status_history`.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.crm.models.customer_status_history import CustomerStatusHistory
from app.shared.base_repository import BaseRepository


class CustomerStatusHistoryRepository(BaseRepository[CustomerStatusHistory]):
    ALLOWED_FIELDS: set[str] = set()

    def __init__(self) -> None:
        super().__init__(CustomerStatusHistory)

    async def list_for_person(
        self, db: AsyncSession, person_id: str
    ) -> list[CustomerStatusHistory]:
        result = await db.execute(
            select(CustomerStatusHistory)
            .where(CustomerStatusHistory.person_id == person_id)
            .order_by(CustomerStatusHistory.changed_at.desc())
        )
        return list(result.scalars().all())


customer_status_history_repository = CustomerStatusHistoryRepository()
