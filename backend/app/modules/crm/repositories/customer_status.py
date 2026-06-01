"""
Repositorios del catálogo CustomerStatus y su matriz. Análogo a `lead_status.py`
SIN `is_won`. Mismas responsabilidades: invariantes (get_by_code, get_initial,
count_initial), resolución batch (list_active, get_by_ids) y el grafo de aristas
(is_allowed, list_outgoing, delete_outgoing, delete_referencing).
"""

from __future__ import annotations

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.crm.models.customer_status import CustomerStatus
from app.modules.crm.models.customer_status_transition import CustomerStatusTransition
from app.shared.base_repository import BaseRepository


class CustomerStatusRepository(BaseRepository[CustomerStatus]):
    ALLOWED_FIELDS: set[str] = {
        "code",
        "name",
        "is_initial",
        "is_final",
        "display_order",
        "active",
        "created_on",
        "updated_on",
    }

    def __init__(self) -> None:
        super().__init__(CustomerStatus)

    async def get_by_code(self, db: AsyncSession, code: str) -> CustomerStatus | None:
        result = await db.execute(
            select(CustomerStatus).where(
                CustomerStatus.code == code, CustomerStatus.deleted_at.is_(None)
            )
        )
        return result.scalars().first()

    async def get_initial(self, db: AsyncSession) -> CustomerStatus | None:
        result = await db.execute(
            select(CustomerStatus).where(
                CustomerStatus.is_initial.is_(True), CustomerStatus.deleted_at.is_(None)
            )
        )
        return result.scalars().first()

    async def count_initial(self, db: AsyncSession, exclude_id: str | None = None) -> int:
        stmt = (
            select(func.count())
            .select_from(CustomerStatus)
            .where(CustomerStatus.is_initial.is_(True), CustomerStatus.deleted_at.is_(None))
        )
        if exclude_id is not None:
            stmt = stmt.where(CustomerStatus.id != exclude_id)
        return (await db.execute(stmt)).scalar_one()

    async def list_active(self, db: AsyncSession) -> list[CustomerStatus]:
        result = await db.execute(
            select(CustomerStatus)
            .where(CustomerStatus.deleted_at.is_(None))
            .order_by(CustomerStatus.display_order.asc(), CustomerStatus.name.asc())
        )
        return list(result.scalars().all())

    async def get_by_ids(self, db: AsyncSession, ids: list[str]) -> list[CustomerStatus]:
        if not ids:
            return []
        result = await db.execute(
            select(CustomerStatus)
            .where(CustomerStatus.id.in_(ids), CustomerStatus.deleted_at.is_(None))
            .order_by(CustomerStatus.display_order.asc(), CustomerStatus.name.asc())
        )
        return list(result.scalars().all())


class CustomerStatusTransitionRepository(BaseRepository[CustomerStatusTransition]):
    ALLOWED_FIELDS: set[str] = set()

    def __init__(self) -> None:
        super().__init__(CustomerStatusTransition)

    async def is_allowed(self, db: AsyncSession, from_id: str, to_id: str) -> bool:
        result = await db.execute(
            select(CustomerStatusTransition.id).where(
                CustomerStatusTransition.from_customer_status_id == from_id,
                CustomerStatusTransition.to_customer_status_id == to_id,
                CustomerStatusTransition.active.is_(True),
            )
        )
        return result.scalars().first() is not None

    async def list_outgoing(self, db: AsyncSession, from_id: str) -> list[str]:
        result = await db.execute(
            select(CustomerStatusTransition.to_customer_status_id).where(
                CustomerStatusTransition.from_customer_status_id == from_id,
                CustomerStatusTransition.active.is_(True),
            )
        )
        return [row[0] for row in result.all()]

    async def delete_outgoing(self, db: AsyncSession, from_id: str) -> None:
        await db.execute(
            delete(CustomerStatusTransition).where(
                CustomerStatusTransition.from_customer_status_id == from_id
            )
        )

    async def delete_referencing(self, db: AsyncSession, status_id: str) -> None:
        await db.execute(
            delete(CustomerStatusTransition).where(
                or_(
                    CustomerStatusTransition.from_customer_status_id == status_id,
                    CustomerStatusTransition.to_customer_status_id == status_id,
                )
            )
        )


customer_status_repository = CustomerStatusRepository()
customer_status_transition_repository = CustomerStatusTransitionRepository()
