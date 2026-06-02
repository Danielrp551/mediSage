"""
Repositorio del timeline (LeadActivity). `list_for_person` devuelve el feed
(active=true), más reciente primero, con filtros tipados por tipo y rango de fecha.
`next_follow_up_map` denormaliza el próximo FOLLOW_UP_SCHEDULED pendiente por persona
para la bandeja del asesor (MyLeadItem.next_follow_up_at).

F5: el composer del asesor (create/update/delete) usa `get_owned` para resolver una
actividad por (id, person_id) y validar ownership (404 ACTIVITY_NOT_FOUND); "borrar"
es `active=false` (no hay SoftDelete).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.crm.enums import ActivityType
from app.modules.crm.models.lead_activity import LeadActivity
from app.shared.base_repository import BaseRepository


class LeadActivityRepository(BaseRepository[LeadActivity]):
    ALLOWED_FIELDS: set[str] = set()  # se lista vía el ActivityListRequest tipado

    def __init__(self) -> None:
        super().__init__(LeadActivity)

    async def list_for_person(
        self,
        db: AsyncSession,
        person_id: str,
        activity_types: list[str] | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> list[LeadActivity]:
        """Timeline de una persona (solo active=true), más reciente primero. Filtra
        por lista de tipos y rango de created_on."""
        stmt = (
            select(LeadActivity)
            .where(
                LeadActivity.person_id == person_id,
                LeadActivity.active.is_(True),
            )
            .order_by(LeadActivity.created_on.desc())
        )
        if activity_types:
            stmt = stmt.where(LeadActivity.activity_type.in_(activity_types))
        if date_from is not None:
            stmt = stmt.where(LeadActivity.created_on >= date_from)
        if date_to is not None:
            stmt = stmt.where(LeadActivity.created_on <= date_to)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_owned(
        self, db: AsyncSession, activity_id: str, person_id: str
    ) -> LeadActivity | None:
        """Resuelve una actividad VIVA (active=true) de una persona — ownership para
        el PUT/DELETE del composer (404 ACTIVITY_NOT_FOUND si no matchea). LeadActivity
        no tiene SoftDelete; "borrada" (active=false) NO se devuelve."""
        result = await db.execute(
            select(LeadActivity).where(
                LeadActivity.id == activity_id,
                LeadActivity.person_id == person_id,
                LeadActivity.active.is_(True),
            )
        )
        return result.scalars().first()

    async def latest_active_at(self, db: AsyncSession, person_id: str) -> datetime | None:
        """`max(created_on)` de las actividades VIVAS (active=true) de la persona, o
        None si no quedan. Lo usa `delete` para recomputar el denormalizado
        `last_activity_at` del lead tras ocultar una actividad."""
        result = await db.execute(
            select(func.max(LeadActivity.created_on)).where(
                LeadActivity.person_id == person_id,
                LeadActivity.active.is_(True),
            )
        )
        return result.scalar()

    async def next_follow_up_map(
        self, db: AsyncSession, person_ids: list[str], now: datetime
    ) -> dict[str, datetime]:
        """person_id → el FOLLOW_UP_SCHEDULED pendiente (futuro, sin completar) más
        próximo. Alimenta MyLeadItem.next_follow_up_at. Vacío hasta que F5 emita
        seguimientos."""
        if not person_ids:
            return {}
        result = await db.execute(
            select(LeadActivity.person_id, func.min(LeadActivity.scheduled_for))
            .where(
                LeadActivity.person_id.in_(person_ids),
                LeadActivity.activity_type == ActivityType.FOLLOW_UP_SCHEDULED.value,
                LeadActivity.active.is_(True),
                LeadActivity.completed_at.is_(None),
                LeadActivity.scheduled_for.isnot(None),
                LeadActivity.scheduled_for >= now,
            )
            .group_by(LeadActivity.person_id)
        )
        return {row[0]: row[1] for row in result.all() if row[1] is not None}


lead_activity_repository = LeadActivityRepository()
