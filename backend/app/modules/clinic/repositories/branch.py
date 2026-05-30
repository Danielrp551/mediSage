"""
Branch repository. `ALLOWED_FIELDS` whitelists which columns the frontend can
filter/sort dynamically via `QueryRequest`. Soft-delete handled by
`BaseRepository` (every read filters `deleted_at IS NULL`).

`count_active_offices` (single, for the delete-with-children guard) and
`count_active_offices_map` (batch, for the denormalized `offices_count`) are
live as of phase 2 now that the Office model exists. "Active" here means
not soft-deleted (a merely disabled office still holds the FK).
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.clinic.models.branch import Branch
from app.modules.clinic.models.office import Office
from app.shared.base_repository import BaseRepository


class BranchRepository(BaseRepository[Branch]):
    ALLOWED_FIELDS: set[str] = {
        "code",
        "name",
        "city",
        "region",
        "country",
        "active",
        "created_on",
        "updated_on",
    }

    def __init__(self) -> None:
        super().__init__(Branch)

    async def get_by_code(self, db: AsyncSession, code: str) -> Branch | None:
        result = await db.execute(
            select(Branch).where(Branch.code == code, Branch.deleted_at.is_(None))
        )
        return result.scalars().first()

    async def list_active(self, db: AsyncSession) -> list[Branch]:
        result = await db.execute(
            select(Branch)
            .where(Branch.active.is_(True), Branch.deleted_at.is_(None))
            .order_by(Branch.name.asc())
        )
        return list(result.scalars().all())

    async def get_by_ids(self, db: AsyncSession, ids: list[str]) -> list[Branch]:
        """Fetch live (non-deleted) branches by id. Additive helper used by
        `staff` to resolve the doctor_branch M:N — a soft-deleted branch is
        filtered out, so it counts as 'unknown' when attaching it to a doctor
        (mirrors vertical_repository.get_by_ids / role_repository.get_by_ids)."""
        if not ids:
            return []
        result = await db.execute(
            select(Branch).where(Branch.id.in_(ids), Branch.deleted_at.is_(None))
        )
        return list(result.scalars().all())

    async def count_active_offices(self, db: AsyncSession, branch_id: str) -> int:
        """Count non-deleted offices under one branch (delete guard)."""
        result = await db.execute(
            select(func.count(Office.id)).where(
                Office.branch_id == branch_id,
                Office.deleted_at.is_(None),
            )
        )
        return result.scalar_one()

    async def count_active_offices_map(
        self, db: AsyncSession, branch_ids: list[str]
    ) -> dict[str, int]:
        """Batch office counts for a page of branches — one query, no N+1.

        Returns a `{branch_id: count}` map; branches with zero offices are
        simply absent (the caller defaults them to 0)."""
        if not branch_ids:
            return {}
        result = await db.execute(
            select(Office.branch_id, func.count(Office.id))
            .where(Office.branch_id.in_(branch_ids), Office.deleted_at.is_(None))
            .group_by(Office.branch_id)
        )
        return {row[0]: row[1] for row in result.all()}


branch_repository = BranchRepository()
