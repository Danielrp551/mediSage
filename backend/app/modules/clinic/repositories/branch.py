"""
Branch repository. `ALLOWED_FIELDS` whitelists which columns the frontend can
filter/sort dynamically via `QueryRequest`. Soft-delete handled by
`BaseRepository` (every read filters `deleted_at IS NULL`).

`count_active_offices` / `count_active_offices_map` (for the delete guard and
the denormalized `offices_count`) land in phase 2 when the Office model exists.
For phase 1 the service layer reports `offices_count = 0`.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.clinic.models.branch import Branch
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


branch_repository = BranchRepository()
