"""
Repositorio del hilo lead activo (PersonLeadStatus). `get_active_for_person`
resuelve la fila viva (UNIQUE parcial ⇒ a lo sumo una). `status_map` /
`last_activity_map` son batch lookups (sin N+1) que alimentan los denormalizados de
PersonItem. `count_using_status` es el guard de DELETE /lead-statuses/{id}
(409 LEAD_STATUS_IN_USE) que F2 difirió y F3 ya puede ejercer (la tabla existe).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.crm.models.lead_status import LeadStatus
from app.modules.crm.models.person_lead_status import PersonLeadStatus
from app.shared.base_repository import BaseRepository


class PersonLeadStatusRepository(BaseRepository[PersonLeadStatus]):
    ALLOWED_FIELDS: set[str] = set()  # nunca se lista directo; se consulta por person_id

    def __init__(self) -> None:
        super().__init__(PersonLeadStatus)

    async def get_active_for_person(
        self, db: AsyncSession, person_id: str
    ) -> PersonLeadStatus | None:
        result = await db.execute(
            select(PersonLeadStatus).where(
                PersonLeadStatus.person_id == person_id,
                PersonLeadStatus.deleted_at.is_(None),
            )
        )
        return result.scalars().first()

    async def status_map(self, db: AsyncSession, person_ids: list[str]) -> dict[str, LeadStatus]:
        """LeadStatus actual de cada persona — una query, sin N+1. Alimenta
        PersonItem.lead_status. Join a través del PersonLeadStatus vivo."""
        if not person_ids:
            return {}
        result = await db.execute(
            select(PersonLeadStatus.person_id, LeadStatus)
            .join(LeadStatus, LeadStatus.id == PersonLeadStatus.lead_status_id)
            .where(
                PersonLeadStatus.person_id.in_(person_ids),
                PersonLeadStatus.deleted_at.is_(None),
            )
        )
        return {row[0]: row[1] for row in result.all()}

    async def last_activity_map(
        self, db: AsyncSession, person_ids: list[str]
    ) -> dict[str, datetime]:
        """last_activity_at por persona (denormalizado) — columna de PersonItem."""
        if not person_ids:
            return {}
        result = await db.execute(
            select(PersonLeadStatus.person_id, PersonLeadStatus.last_activity_at).where(
                PersonLeadStatus.person_id.in_(person_ids),
                PersonLeadStatus.deleted_at.is_(None),
            )
        )
        return {row[0]: row[1] for row in result.all() if row[1] is not None}

    async def count_using_status(self, db: AsyncSession, lead_status_id: str) -> int:
        """Guard de DELETE /lead-statuses/{id} (409 LEAD_STATUS_IN_USE): cuenta los
        PersonLeadStatus vivos que lo referencian."""
        result = await db.execute(
            select(func.count())
            .select_from(PersonLeadStatus)
            .where(
                PersonLeadStatus.lead_status_id == lead_status_id,
                PersonLeadStatus.deleted_at.is_(None),
            )
        )
        return result.scalar_one()


person_lead_status_repository = PersonLeadStatusRepository()
