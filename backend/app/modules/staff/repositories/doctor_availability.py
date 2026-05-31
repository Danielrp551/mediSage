"""
DoctorAvailability repository. Lectura vía `list_for_doctor` (rango de fechas);
escritura por bloque. No hay endpoint `/list`, así que `ALLOWED_FIELDS` queda
vacío.

`branch_name_map` y `office_map` son lookups batch (una query) para denormalizar
branch_name / office_code / office_name en los Item sin N+1 — el bloque no tiene
relación ORM a branch/office (solo `doctor`), así que los nombres se resuelven acá.
"""

from __future__ import annotations

from datetime import date as date_type

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.clinic.models.branch import Branch
from app.modules.clinic.models.office import Office
from app.modules.staff.models.doctor_availability import DoctorAvailability
from app.shared.base_repository import BaseRepository


class DoctorAvailabilityRepository(BaseRepository[DoctorAvailability]):
    ALLOWED_FIELDS: set[str] = set()

    def __init__(self) -> None:
        super().__init__(DoctorAvailability)

    async def list_for_doctor(
        self,
        db: AsyncSession,
        doctor_id: str,
        date_from: date_type | None = None,
        date_to: date_type | None = None,
    ) -> list[DoctorAvailability]:
        """Bloques de un doctor en un rango inclusivo de fechas. `from`/`to`
        filtran la columna `date` (BETWEEN). Ordenados por date → opens_at para
        la grilla del calendario."""
        stmt = (
            select(DoctorAvailability)
            .where(
                DoctorAvailability.doctor_id == doctor_id,
                DoctorAvailability.deleted_at.is_(None),
            )
            .order_by(
                DoctorAvailability.date.asc(),
                DoctorAvailability.opens_at.asc(),
            )
        )
        if date_from is not None:
            stmt = stmt.where(DoctorAvailability.date >= date_from)
        if date_to is not None:
            stmt = stmt.where(DoctorAvailability.date <= date_to)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def list_for_doctor_on_date(
        self, db: AsyncSession, doctor_id: str, on_date: date_type
    ) -> list[DoctorAvailability]:
        """Todos los bloques vivos de un doctor en una fecha — usado por el
        invariante de solape (#3) para chequear el bloque entrante vs los existentes."""
        return await self.list_for_doctor(db, doctor_id, on_date, on_date)

    async def branch_name_map(self, db: AsyncSession, branch_ids: list[str]) -> dict[str, str]:
        """Batch de nombres de sede para el denormalizado branch_name."""
        if not branch_ids:
            return {}
        result = await db.execute(select(Branch.id, Branch.name).where(Branch.id.in_(branch_ids)))
        return {row[0]: row[1] for row in result.all()}

    async def office_map(
        self, db: AsyncSession, office_ids: list[str]
    ) -> dict[str, tuple[str, str]]:
        """Batch de `(code, name)` de consultorio por id, para los denormalizados
        office_code / office_name."""
        if not office_ids:
            return {}
        result = await db.execute(
            select(Office.id, Office.code, Office.name).where(Office.id.in_(office_ids))
        )
        return {row[0]: (row[1], row[2]) for row in result.all()}


doctor_availability_repository = DoctorAvailabilityRepository()
