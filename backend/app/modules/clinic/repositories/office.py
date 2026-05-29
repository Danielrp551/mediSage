"""
Office repository. `ALLOWED_FIELDS` whitelists the columns the frontend can
filter/sort dynamically via `QueryRequest` — `branch_id` is included so the
Offices page can filter by parent branch. Soft-delete handled by
`BaseRepository` (every read filters `deleted_at IS NULL`).

`get_full` eager-loads the parent branch and the apt verticals, filtering out
soft-deleted verticals via `with_loader_criteria` so the M:N respects catalog's
soft-delete WITHOUT coupling clinic to catalog's delete guard. The
`count_apt_verticals_map` / `branch_name_map` pair powers the denormalized
`verticals_count` / `branch_name` on each OfficeItem (batched, never N+1).
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, with_loader_criteria

from app.modules.catalog.models.vertical import Vertical
from app.modules.clinic.models.associations import office_vertical
from app.modules.clinic.models.branch import Branch
from app.modules.clinic.models.office import Office
from app.shared.base_repository import BaseRepository


class OfficeRepository(BaseRepository[Office]):
    ALLOWED_FIELDS: set[str] = {
        "branch_id",
        "code",
        "name",
        "floor",
        "active",
        "created_on",
        "updated_on",
    }

    def __init__(self) -> None:
        super().__init__(Office)

    async def get_by_branch_and_code(
        self, db: AsyncSession, branch_id: str, code: str
    ) -> Office | None:
        result = await db.execute(
            select(Office).where(
                Office.branch_id == branch_id,
                Office.code == code,
                Office.deleted_at.is_(None),
            )
        )
        return result.scalars().first()

    async def get_full(self, db: AsyncSession, office_id: str) -> Office | None:
        # Eager-load the parent branch and the apt verticals, filtering out
        # soft-deleted verticals via `with_loader_criteria` so the M:N load
        # respects catalog's soft-delete WITHOUT clinic coupling to catalog's
        # delete guard (the office_vertical row may still exist; we just don't
        # surface a dead vertical).
        return await self.get_by_id(
            db,
            office_id,
            load=(
                selectinload(Office.branch),
                selectinload(Office.verticals),
                with_loader_criteria(Vertical, Vertical.deleted_at.is_(None), include_aliases=True),
            ),
        )

    async def list_active(
        self,
        db: AsyncSession,
        branch_id: str | None = None,
        vertical_id: str | None = None,
    ) -> list[Office]:
        # No eager-load: the only consumer maps rows to OfficeOption, which
        # never touches branch/verticals. `vertical_id` filters via an EXISTS
        # join on office_vertical (the office must be apt for that vertical
        # AND the vertical must be alive).
        stmt = (
            select(Office)
            .where(Office.active.is_(True), Office.deleted_at.is_(None))
            .order_by(Office.code.asc())
        )
        if branch_id is not None:
            stmt = stmt.where(Office.branch_id == branch_id)
        if vertical_id is not None:
            stmt = stmt.where(
                select(office_vertical.c.office_id)
                .join(Vertical, Vertical.id == office_vertical.c.vertical_id)
                .where(
                    office_vertical.c.office_id == Office.id,
                    office_vertical.c.vertical_id == vertical_id,
                    Vertical.deleted_at.is_(None),
                )
                .exists()
            )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def count_apt_verticals_map(
        self, db: AsyncSession, office_ids: list[str]
    ) -> dict[str, int]:
        """Batch count of apt, non-deleted verticals per office — one query,
        no N+1. Powers OfficeItem.verticals_count. Joins through the M:N and
        filters deleted verticals so disabled/removed catalog rows don't count."""
        if not office_ids:
            return {}
        result = await db.execute(
            select(office_vertical.c.office_id, func.count(office_vertical.c.vertical_id))
            .join(Vertical, Vertical.id == office_vertical.c.vertical_id)
            .where(
                office_vertical.c.office_id.in_(office_ids),
                Vertical.deleted_at.is_(None),
            )
            .group_by(office_vertical.c.office_id)
        )
        return {row[0]: row[1] for row in result.all()}

    async def branch_name_map(self, db: AsyncSession, branch_ids: list[str]) -> dict[str, str]:
        """Batch branch names for the denormalized OfficeItem.branch_name."""
        if not branch_ids:
            return {}
        result = await db.execute(select(Branch.id, Branch.name).where(Branch.id.in_(branch_ids)))
        return {row[0]: row[1] for row in result.all()}


office_repository = OfficeRepository()
