"""
Repositorios del catálogo LeadStatus y de su matriz de transiciones (ADR-008).

`LeadStatusRepository`: CRUD del catálogo + helpers de invariantes (get_by_code,
get_initial, count_initial) y resolución batch (list_active, get_by_ids).

`LeadStatusTransitionRepository`: el grafo de aristas. `is_allowed` es el core que
consumirá el transition service (F3). `list_outgoing`/`delete_outgoing` sostienen
el editor de matriz (GET/PUT /{id}/transitions). `delete_referencing` limpia las
aristas colgantes al borrar un estado (las tablas de transición no tienen
soft-delete → DELETE real).
"""

from __future__ import annotations

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.crm.models.lead_status import LeadStatus
from app.modules.crm.models.lead_status_transition import LeadStatusTransition
from app.shared.base_repository import BaseRepository


class LeadStatusRepository(BaseRepository[LeadStatus]):
    ALLOWED_FIELDS: set[str] = {
        "code",
        "name",
        "is_initial",
        "is_final",
        "is_won",
        "display_order",
        "active",
        "created_on",
        "updated_on",
    }

    def __init__(self) -> None:
        super().__init__(LeadStatus)

    async def get_by_code(self, db: AsyncSession, code: str) -> LeadStatus | None:
        result = await db.execute(
            select(LeadStatus).where(LeadStatus.code == code, LeadStatus.deleted_at.is_(None))
        )
        return result.scalars().first()

    async def get_initial(self, db: AsyncSession) -> LeadStatus | None:
        """El único estado is_initial (NO_INITIAL_LEAD_STATUS si no hay — F3)."""
        result = await db.execute(
            select(LeadStatus).where(
                LeadStatus.is_initial.is_(True), LeadStatus.deleted_at.is_(None)
            )
        )
        return result.scalars().first()

    async def get_won(self, db: AsyncSession) -> LeadStatus | None:
        """El estado GANADO del funnel (is_won) — resuelto por flag, no por code en duro:
        renombrar el code en el catálogo no rompe las automatizaciones. Si hubiera varios
        is_won, gana el de menor display_order."""
        result = await db.execute(
            select(LeadStatus)
            .where(LeadStatus.is_won.is_(True), LeadStatus.deleted_at.is_(None))
            .order_by(LeadStatus.display_order)
        )
        return result.scalars().first()

    async def count_initial(self, db: AsyncSession, exclude_id: str | None = None) -> int:
        """Guard de "exactamente un is_initial". Lo usa create/update para detectar
        un segundo inicial (MULTIPLE_INITIAL_STATUS)."""
        stmt = (
            select(func.count())
            .select_from(LeadStatus)
            .where(LeadStatus.is_initial.is_(True), LeadStatus.deleted_at.is_(None))
        )
        if exclude_id is not None:
            stmt = stmt.where(LeadStatus.id != exclude_id)
        return (await db.execute(stmt)).scalar_one()

    async def list_active(self, db: AsyncSession) -> list[LeadStatus]:
        """Estados vivos ordenados por display_order — GET /active y resolución de
        Options del editor de matriz."""
        result = await db.execute(
            select(LeadStatus)
            .where(LeadStatus.deleted_at.is_(None))
            .order_by(LeadStatus.display_order.asc(), LeadStatus.name.asc())
        )
        return list(result.scalars().all())

    async def get_by_ids(self, db: AsyncSession, ids: list[str]) -> list[LeadStatus]:
        """Estados vivos para una lista de ids, ordenados por display_order. Resuelve
        los `to_ids` de una transición a Options."""
        if not ids:
            return []
        result = await db.execute(
            select(LeadStatus)
            .where(LeadStatus.id.in_(ids), LeadStatus.deleted_at.is_(None))
            .order_by(LeadStatus.display_order.asc(), LeadStatus.name.asc())
        )
        return list(result.scalars().all())


class LeadStatusTransitionRepository(BaseRepository[LeadStatusTransition]):
    ALLOWED_FIELDS: set[str] = set()

    def __init__(self) -> None:
        super().__init__(LeadStatusTransition)

    async def is_allowed(self, db: AsyncSession, from_id: str, to_id: str) -> bool:
        """Core del enforcement de transición (ADR-008, consumido en F3)."""
        result = await db.execute(
            select(LeadStatusTransition.id).where(
                LeadStatusTransition.from_lead_status_id == from_id,
                LeadStatusTransition.to_lead_status_id == to_id,
                LeadStatusTransition.active.is_(True),
            )
        )
        return result.scalars().first() is not None

    async def list_outgoing(self, db: AsyncSession, from_id: str) -> list[str]:
        """to_ids alcanzables desde un estado — GET /lead-statuses/{id}/transitions."""
        result = await db.execute(
            select(LeadStatusTransition.to_lead_status_id).where(
                LeadStatusTransition.from_lead_status_id == from_id,
                LeadStatusTransition.active.is_(True),
            )
        )
        return [row[0] for row in result.all()]

    async def delete_outgoing(self, db: AsyncSession, from_id: str) -> None:
        """Borra todas las aristas de salida de un estado (sin SD → DELETE real). El
        service inserta luego el set nuevo (necesita audit columns). Una sola tx."""
        await db.execute(
            delete(LeadStatusTransition).where(LeadStatusTransition.from_lead_status_id == from_id)
        )

    async def delete_referencing(self, db: AsyncSession, status_id: str) -> None:
        """Borra cualquier arista que toque el estado (entrante o saliente) al
        eliminarlo, para no dejar aristas colgantes en la matriz."""
        await db.execute(
            delete(LeadStatusTransition).where(
                or_(
                    LeadStatusTransition.from_lead_status_id == status_id,
                    LeadStatusTransition.to_lead_status_id == status_id,
                )
            )
        )


lead_status_repository = LeadStatusRepository()
lead_status_transition_repository = LeadStatusTransitionRepository()
