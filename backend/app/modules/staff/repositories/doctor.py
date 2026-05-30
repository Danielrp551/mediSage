"""
Doctor repository. `ALLOWED_FIELDS` whitelist las columnas que el frontend puede
filtrar/ordenar dinámicamente vía `QueryRequest`. `full_name`/`email` NO están
(no son columnas de doctor — viven en admin.User; el filtro por nombre es
client-side). Soft-delete lo maneja `BaseRepository` (todo read filtra
`deleted_at IS NULL`).

`get_full` carga eager el User 1:1 y los M:N (branches/verticals), filtrando las
sedes/verticales soft-deleted vía `with_loader_criteria` para que el M:N respete
el soft-delete de clinic/catalog SIN acoplar staff a sus delete guards. Los pares
`count_branches_map` / `count_verticals_map` alimentan los denormalizados
`branches_count` / `verticals_count` de cada DoctorItem (batch, nunca N+1).
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, with_loader_criteria

from app.modules.catalog.models.vertical import Vertical
from app.modules.clinic.models.branch import Branch
from app.modules.staff.models.associations import doctor_branch, doctor_vertical
from app.modules.staff.models.doctor import Doctor
from app.shared.base_repository import BaseRepository


class DoctorRepository(BaseRepository[Doctor]):
    ALLOWED_FIELDS: set[str] = {
        "cmp_code",
        "slot_duration_min",
        "active",
        "created_on",
        "updated_on",
    }

    def __init__(self) -> None:
        super().__init__(Doctor)

    async def get_by_user_id(self, db: AsyncSession, user_id: str) -> Doctor | None:
        result = await db.execute(
            select(Doctor).where(Doctor.user_id == user_id, Doctor.deleted_at.is_(None))
        )
        return result.scalars().first()

    async def get_full(self, db: AsyncSession, doctor_id: str) -> Doctor | None:
        # Eager-load el User 1:1 y los M:N, filtrando sedes/verticales
        # soft-deleted vía `with_loader_criteria` (la fila de asociación puede
        # seguir existiendo; simplemente no exponemos una sede/vertical muerta).
        return await self.get_by_id(
            db,
            doctor_id,
            load=(
                selectinload(Doctor.user),
                selectinload(Doctor.branches),
                selectinload(Doctor.verticals),
                with_loader_criteria(Branch, Branch.deleted_at.is_(None), include_aliases=True),
                with_loader_criteria(Vertical, Vertical.deleted_at.is_(None), include_aliases=True),
            ),
        )

    async def list_active(
        self,
        db: AsyncSession,
        branch_id: str | None = None,
        vertical_id: str | None = None,
    ) -> list[Doctor]:
        # Carga el User (el DoctorOption necesita full_name). Filtra opcionalmente
        # por sede/vertical vía EXISTS sobre las tablas M:N (el doctor debe estar
        # asignado a esa sede / cubrir esa vertical, y la sede/vertical viva).
        stmt = (
            select(Doctor)
            .where(Doctor.active.is_(True), Doctor.deleted_at.is_(None))
            .options(selectinload(Doctor.user))
            .order_by(Doctor.created_on.asc())
        )
        if branch_id is not None:
            stmt = stmt.where(
                select(doctor_branch.c.doctor_id)
                .join(Branch, Branch.id == doctor_branch.c.branch_id)
                .where(
                    doctor_branch.c.doctor_id == Doctor.id,
                    doctor_branch.c.branch_id == branch_id,
                    Branch.deleted_at.is_(None),
                )
                .exists()
            )
        if vertical_id is not None:
            stmt = stmt.where(
                select(doctor_vertical.c.doctor_id)
                .join(Vertical, Vertical.id == doctor_vertical.c.vertical_id)
                .where(
                    doctor_vertical.c.doctor_id == Doctor.id,
                    doctor_vertical.c.vertical_id == vertical_id,
                    Vertical.deleted_at.is_(None),
                )
                .exists()
            )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def count_branches_map(self, db: AsyncSession, doctor_ids: list[str]) -> dict[str, int]:
        """Conteo batch de sedes vivas por doctor — una query, sin N+1. Alimenta
        DoctorItem.branches_count. Filtra sedes soft-deleted."""
        if not doctor_ids:
            return {}
        result = await db.execute(
            select(doctor_branch.c.doctor_id, func.count(doctor_branch.c.branch_id))
            .join(Branch, Branch.id == doctor_branch.c.branch_id)
            .where(
                doctor_branch.c.doctor_id.in_(doctor_ids),
                Branch.deleted_at.is_(None),
            )
            .group_by(doctor_branch.c.doctor_id)
        )
        return {row[0]: row[1] for row in result.all()}

    async def count_verticals_map(self, db: AsyncSession, doctor_ids: list[str]) -> dict[str, int]:
        """Conteo batch de verticales vivas por doctor — una query, sin N+1.
        Alimenta DoctorItem.verticals_count. Filtra verticales soft-deleted."""
        if not doctor_ids:
            return {}
        result = await db.execute(
            select(doctor_vertical.c.doctor_id, func.count(doctor_vertical.c.vertical_id))
            .join(Vertical, Vertical.id == doctor_vertical.c.vertical_id)
            .where(
                doctor_vertical.c.doctor_id.in_(doctor_ids),
                Vertical.deleted_at.is_(None),
            )
            .group_by(doctor_vertical.c.doctor_id)
        )
        return {row[0]: row[1] for row in result.all()}


doctor_repository = DoctorRepository()
