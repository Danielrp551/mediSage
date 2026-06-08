"""
Repositorios del catálogo AppointmentStatus y de su matriz de transiciones
(ADR-008). Espejan crm.lead_status (sin el extra de `is_won`).

`AppointmentStatusRepository`: CRUD del catálogo + helpers de invariantes
(get_by_code, get_initial, count_initial) y resolución batch (list_active,
get_by_ids).

`AppointmentStatusTransitionRepository`: el grafo de aristas. `is_allowed` es el
core que consumirá el transition service (F3). `list_outgoing`/`delete_outgoing`
sostienen el editor de matriz (GET/PUT /{id}/transitions). `delete_referencing`
limpia las aristas colgantes al borrar un estado (las tablas de transición no
tienen soft-delete → DELETE real).
"""

from __future__ import annotations

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.scheduling.models.appointment_status import AppointmentStatus
from app.modules.scheduling.models.appointment_status_transition import (
    AppointmentStatusTransition,
)
from app.shared.base_repository import BaseRepository


class AppointmentStatusRepository(BaseRepository[AppointmentStatus]):
    ALLOWED_FIELDS: set[str] = {
        "code",
        "name",
        "is_initial",
        "is_final",
        "is_active_attention",
        "display_order",
        "active",
        "created_on",
        "updated_on",
    }

    def __init__(self) -> None:
        super().__init__(AppointmentStatus)

    async def get_by_code(self, db: AsyncSession, code: str) -> AppointmentStatus | None:
        result = await db.execute(
            select(AppointmentStatus).where(
                AppointmentStatus.code == code, AppointmentStatus.deleted_at.is_(None)
            )
        )
        return result.scalars().first()

    async def get_initial(self, db: AsyncSession) -> AppointmentStatus | None:
        """El único estado is_initial (NO_INITIAL_STATUS si no hay — F2)."""
        result = await db.execute(
            select(AppointmentStatus).where(
                AppointmentStatus.is_initial.is_(True),
                AppointmentStatus.deleted_at.is_(None),
            )
        )
        return result.scalars().first()

    async def count_initial(self, db: AsyncSession, exclude_id: str | None = None) -> int:
        """Guard de "exactamente un is_initial". Lo usa create/update para detectar
        un segundo inicial (MULTIPLE_INITIAL_STATUS)."""
        stmt = (
            select(func.count())
            .select_from(AppointmentStatus)
            .where(
                AppointmentStatus.is_initial.is_(True),
                AppointmentStatus.deleted_at.is_(None),
            )
        )
        if exclude_id is not None:
            stmt = stmt.where(AppointmentStatus.id != exclude_id)
        return (await db.execute(stmt)).scalar_one()

    async def list_active(self, db: AsyncSession) -> list[AppointmentStatus]:
        """Estados vivos ordenados por display_order — GET /active y resolución de
        Options del editor de matriz."""
        result = await db.execute(
            select(AppointmentStatus)
            .where(AppointmentStatus.deleted_at.is_(None))
            .order_by(AppointmentStatus.display_order.asc(), AppointmentStatus.name.asc())
        )
        return list(result.scalars().all())

    async def get_by_ids(self, db: AsyncSession, ids: list[str]) -> list[AppointmentStatus]:
        """Estados vivos para una lista de ids, ordenados por display_order. Resuelve
        los `to_ids` de una transición a Options."""
        if not ids:
            return []
        result = await db.execute(
            select(AppointmentStatus)
            .where(AppointmentStatus.id.in_(ids), AppointmentStatus.deleted_at.is_(None))
            .order_by(AppointmentStatus.display_order.asc(), AppointmentStatus.name.asc())
        )
        return list(result.scalars().all())

    async def get_by_ids_for_badge(
        self, db: AsyncSession, ids: list[str]
    ) -> list[AppointmentStatus]:
        """Como get_by_ids pero INCLUYE soft-deleted: para denormalizar el badge de una
        cita cuyo estado se soft-deleteó (defensa en profundidad — la lectura nunca debe
        500-ear por un estado borrado; lookup puro por id, como office_map/person_name_map)."""
        if not ids:
            return []
        result = await db.execute(select(AppointmentStatus).where(AppointmentStatus.id.in_(ids)))
        return list(result.scalars().all())


class AppointmentStatusTransitionRepository(BaseRepository[AppointmentStatusTransition]):
    ALLOWED_FIELDS: set[str] = set()

    def __init__(self) -> None:
        super().__init__(AppointmentStatusTransition)

    async def is_allowed(self, db: AsyncSession, from_id: str, to_id: str) -> bool:
        """Core del enforcement de transición (ADR-008, consumido en F3)."""
        result = await db.execute(
            select(AppointmentStatusTransition.id).where(
                AppointmentStatusTransition.from_status_id == from_id,
                AppointmentStatusTransition.to_status_id == to_id,
                AppointmentStatusTransition.active.is_(True),
            )
        )
        return result.scalars().first() is not None

    async def list_outgoing(self, db: AsyncSession, from_id: str) -> list[str]:
        """to_ids alcanzables desde un estado — GET /appointment-statuses/{id}/transitions."""
        result = await db.execute(
            select(AppointmentStatusTransition.to_status_id).where(
                AppointmentStatusTransition.from_status_id == from_id,
                AppointmentStatusTransition.active.is_(True),
            )
        )
        return [row[0] for row in result.all()]

    async def delete_outgoing(self, db: AsyncSession, from_id: str) -> None:
        """Borra todas las aristas de salida de un estado (sin SD → DELETE real). El
        service inserta luego el set nuevo (necesita audit columns). Una sola tx."""
        await db.execute(
            delete(AppointmentStatusTransition).where(
                AppointmentStatusTransition.from_status_id == from_id
            )
        )

    async def delete_referencing(self, db: AsyncSession, status_id: str) -> None:
        """Borra cualquier arista que toque el estado (entrante o saliente) al
        eliminarlo, para no dejar aristas colgantes en la matriz."""
        await db.execute(
            delete(AppointmentStatusTransition).where(
                or_(
                    AppointmentStatusTransition.from_status_id == status_id,
                    AppointmentStatusTransition.to_status_id == status_id,
                )
            )
        )


appointment_status_repository = AppointmentStatusRepository()
appointment_status_transition_repository = AppointmentStatusTransitionRepository()
