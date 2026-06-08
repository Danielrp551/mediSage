"""
Repositorio de Appointment: chequeo de conflicto (solape) + rango (disponibilidad) +
batch maps de denormalización (sin N+1).

⚠ El solape exacto se calcula en el SERVICE (Python), NO en SQL: `make_interval` es
Postgres-only y el smoke corre en sqlite. Estos métodos traen una VENTANA amplia de
citas por `scheduled_for` (con un back-buffer de 1 día que cubre cualquier
`duration_min` realista) y el service filtra el solape real con `timedelta`. El
`SELECT … FOR UPDATE` (Postgres) bloquea las citas solapantes EXISTENTES; el caso de
un slot VACÍO (sin fila previa que lockear) lo cubre un advisory lock por doctor/office
en el service (ver availability._acquire_booking_locks). En sqlite ambos son no-op.

Los batch maps son SELECTs directos sobre los modelos de los otros módulos (Product no
expone get_by_ids; Person/User no tienen `full_name` columna → se compone). Lookups
puros por id (sin filtrar deleted_at) para mostrar el nombre aunque la entidad se haya
soft-deleteado luego — consistente con staff.doctor_availability_repository.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.modules.admin.models.user import User
from app.modules.catalog.models.product import Product
from app.modules.clinic.models.branch import Branch
from app.modules.clinic.models.office import Office
from app.modules.crm.models.person import Person
from app.modules.scheduling.models.appointment import Appointment
from app.modules.staff.models.doctor import Doctor
from app.shared.base_repository import BaseRepository

# Back-buffer para la ventana de citas candidatas al solape: una cita que empieza antes
# del rango puede extenderse dentro de él. 1 día cubre cualquier duración realista.
_OVERLAP_BACK_BUFFER = timedelta(days=1)


def _compose_name(first: str, last: str, second: str | None) -> str:
    return f"{first} {last} {second or ''}".strip()


class AppointmentRepository(BaseRepository[Appointment]):
    # SOLO columnas reales de `appointment`. Los *_name/status son DENORM → NO acá
    # (lección cd10c78). Default sort = scheduled_for asc (lo fija el front).
    ALLOWED_FIELDS: set[str] = {
        "person_id",
        "doctor_id",
        "office_id",
        "branch_id",
        "product_id",
        "status_id",
        "source",
        "scheduled_for",
        "active",
        "created_on",
        "updated_on",
    }

    def __init__(self) -> None:
        super().__init__(Appointment)

    async def _list_blocking(
        self,
        db: AsyncSession,
        column: InstrumentedAttribute[str],
        value: str,
        *,
        start: datetime,
        end: datetime,
        blocking_status_ids: list[str],
        exclude_id: str | None,
        for_update: bool,
    ) -> list[Appointment]:
        stmt = (
            select(Appointment)
            .where(
                column == value,
                Appointment.deleted_at.is_(None),
                Appointment.status_id.in_(blocking_status_ids),
                Appointment.scheduled_for >= start - _OVERLAP_BACK_BUFFER,
                Appointment.scheduled_for < end,
            )
            .order_by(Appointment.scheduled_for.asc())
        )
        if exclude_id is not None:
            stmt = stmt.where(Appointment.id != exclude_id)
        if for_update:
            stmt = stmt.with_for_update()
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def list_blocking_for_doctor(
        self,
        db: AsyncSession,
        doctor_id: str,
        *,
        start: datetime,
        end: datetime,
        blocking_status_ids: list[str],
        exclude_id: str | None = None,
        for_update: bool = False,
    ) -> list[Appointment]:
        """Citas del doctor (en estados que ocupan tiempo) en una ventana alrededor de
        [start, end). El service filtra el solape exacto. for_update → SLOT_TAKEN (#5)."""
        return await self._list_blocking(
            db,
            Appointment.doctor_id,
            doctor_id,
            start=start,
            end=end,
            blocking_status_ids=blocking_status_ids,
            exclude_id=exclude_id,
            for_update=for_update,
        )

    async def list_blocking_for_office(
        self,
        db: AsyncSession,
        office_id: str,
        *,
        start: datetime,
        end: datetime,
        blocking_status_ids: list[str],
        exclude_id: str | None = None,
        for_update: bool = False,
    ) -> list[Appointment]:
        """Igual que el del doctor pero por office (OFFICE_SLOT_TAKEN, #6)."""
        return await self._list_blocking(
            db,
            Appointment.office_id,
            office_id,
            start=start,
            end=end,
            blocking_status_ids=blocking_status_ids,
            exclude_id=exclude_id,
            for_update=for_update,
        )

    async def list_in_range(
        self,
        db: AsyncSession,
        *,
        doctor_id: str | None = None,
        office_id: str | None = None,
        branch_id: str | None = None,
        start: datetime,
        end: datetime,
        status_ids: list[str] | None = None,
    ) -> list[Appointment]:
        """Citas que pueden solapar [start, end) (con back-buffer) para el algoritmo de
        disponibilidad (resta las ocupadas del doctor) y, en F4, el calendario. El
        solape exacto lo filtra el caller en Python."""
        stmt = (
            select(Appointment)
            .where(
                Appointment.deleted_at.is_(None),
                Appointment.scheduled_for >= start - _OVERLAP_BACK_BUFFER,
                Appointment.scheduled_for < end,
            )
            .order_by(Appointment.scheduled_for.asc())
        )
        if doctor_id is not None:
            stmt = stmt.where(Appointment.doctor_id == doctor_id)
        if office_id is not None:
            stmt = stmt.where(Appointment.office_id == office_id)
        if branch_id is not None:
            stmt = stmt.where(Appointment.branch_id == branch_id)
        if status_ids is not None:
            stmt = stmt.where(Appointment.status_id.in_(status_ids))
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def count_using_status(self, db: AsyncSession, status_id: str) -> int:
        """Citas vivas en un estado dado — delete-guard APPOINTMENT_STATUS_IN_USE."""
        result = await db.execute(
            select(func.count())
            .select_from(Appointment)
            .where(Appointment.status_id == status_id, Appointment.deleted_at.is_(None))
        )
        return result.scalar_one()

    # ── Batch maps de denormalización (sin N+1) ───────────────────────

    async def person_name_map(self, db: AsyncSession, person_ids: list[str]) -> dict[str, str]:
        if not person_ids:
            return {}
        rows = await db.execute(
            select(Person.id, Person.first_name, Person.last_name, Person.second_last_name).where(
                Person.id.in_(person_ids)
            )
        )
        return {r.id: _compose_name(r.first_name, r.last_name, r.second_last_name) for r in rows}

    async def doctor_name_map(self, db: AsyncSession, doctor_ids: list[str]) -> dict[str, str]:
        if not doctor_ids:
            return {}
        rows = await db.execute(
            select(Doctor.id, User.first_name, User.last_name, User.second_last_name)
            .join(User, Doctor.user_id == User.id)
            .where(Doctor.id.in_(doctor_ids))
        )
        return {r.id: _compose_name(r.first_name, r.last_name, r.second_last_name) for r in rows}

    async def office_map(
        self, db: AsyncSession, office_ids: list[str]
    ) -> dict[str, tuple[str, str]]:
        """{office_id: (name, branch_id)}."""
        if not office_ids:
            return {}
        rows = await db.execute(
            select(Office.id, Office.name, Office.branch_id).where(Office.id.in_(office_ids))
        )
        return {r.id: (r.name, r.branch_id) for r in rows}

    async def branch_name_map(self, db: AsyncSession, branch_ids: list[str]) -> dict[str, str]:
        if not branch_ids:
            return {}
        rows = await db.execute(select(Branch.id, Branch.name).where(Branch.id.in_(branch_ids)))
        return {r.id: r.name for r in rows}

    async def product_name_map(self, db: AsyncSession, product_ids: list[str]) -> dict[str, str]:
        if not product_ids:
            return {}
        rows = await db.execute(select(Product.id, Product.name).where(Product.id.in_(product_ids)))
        return {r.id: r.name for r in rows}


appointment_repository = AppointmentRepository()
