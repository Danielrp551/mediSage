"""
Repositorio del hilo cliente activo (PersonCustomerStatus). `get_active_for_person`
resuelve la fila viva (UNIQUE parcial ⇒ a lo sumo una). `status_map` es un batch
lookup (sin N+1) que alimenta el denormalizado `customer_status` de PersonItem.
`count_using_status` es el guard de DELETE /customer-statuses/{id}
(409 CUSTOMER_STATUS_IN_USE) que F2 difirió y F4 ya puede ejercer (la tabla existe).
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.crm.models.customer_status import CustomerStatus
from app.modules.crm.models.person_customer_status import PersonCustomerStatus
from app.shared.base_repository import BaseRepository


class PersonCustomerStatusRepository(BaseRepository[PersonCustomerStatus]):
    ALLOWED_FIELDS: set[str] = set()  # nunca se lista directo; se consulta por person_id

    def __init__(self) -> None:
        super().__init__(PersonCustomerStatus)

    async def get_active_for_person(
        self, db: AsyncSession, person_id: str
    ) -> PersonCustomerStatus | None:
        result = await db.execute(
            select(PersonCustomerStatus).where(
                PersonCustomerStatus.person_id == person_id,
                PersonCustomerStatus.deleted_at.is_(None),
            )
        )
        return result.scalars().first()

    async def status_map(
        self, db: AsyncSession, person_ids: list[str]
    ) -> dict[str, CustomerStatus]:
        """CustomerStatus actual de cada persona — una query, sin N+1. Alimenta
        PersonItem.customer_status. Join a través del PersonCustomerStatus vivo."""
        if not person_ids:
            return {}
        result = await db.execute(
            select(PersonCustomerStatus.person_id, CustomerStatus)
            .join(CustomerStatus, CustomerStatus.id == PersonCustomerStatus.customer_status_id)
            .where(
                PersonCustomerStatus.person_id.in_(person_ids),
                PersonCustomerStatus.deleted_at.is_(None),
            )
        )
        return {row[0]: row[1] for row in result.all()}

    async def count_using_status(self, db: AsyncSession, customer_status_id: str) -> int:
        """Guard de DELETE /customer-statuses/{id} (409 CUSTOMER_STATUS_IN_USE): cuenta
        los PersonCustomerStatus vivos que lo referencian."""
        result = await db.execute(
            select(func.count())
            .select_from(PersonCustomerStatus)
            .where(
                PersonCustomerStatus.customer_status_id == customer_status_id,
                PersonCustomerStatus.deleted_at.is_(None),
            )
        )
        return result.scalar_one()


person_customer_status_repository = PersonCustomerStatusRepository()
