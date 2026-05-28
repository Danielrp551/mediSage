"""
Vertical repository. `ALLOWED_FIELDS` whitelists which columns the frontend
can filter/sort dynamically via `QueryRequest`. Soft-delete handled by
`BaseRepository` (every read filters `deleted_at IS NULL`).

`count_active_services` / `count_active_products` are added in later phases
when Service and Product models exist. For phase 1, the service layer
hardcodes those counts to 0 so the `VerticalItem` envelope stays stable.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.models.vertical import Vertical
from app.shared.base_repository import BaseRepository


class VerticalRepository(BaseRepository[Vertical]):
    ALLOWED_FIELDS: set[str] = {
        "code",
        "name",
        "active",
        "display_order",
        "created_on",
        "updated_on",
    }

    def __init__(self) -> None:
        super().__init__(Vertical)

    async def get_by_code(self, db: AsyncSession, code: str) -> Vertical | None:
        result = await db.execute(
            select(Vertical).where(Vertical.code == code, Vertical.deleted_at.is_(None))
        )
        return result.scalars().first()

    async def list_active(self, db: AsyncSession) -> list[Vertical]:
        result = await db.execute(
            select(Vertical)
            .where(Vertical.active.is_(True), Vertical.deleted_at.is_(None))
            .order_by(Vertical.display_order.asc(), Vertical.name.asc())
        )
        return list(result.scalars().all())


vertical_repository = VerticalRepository()
