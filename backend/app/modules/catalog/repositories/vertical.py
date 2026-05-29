"""
Vertical repository. `ALLOWED_FIELDS` whitelists which columns the frontend
can filter/sort dynamically via `QueryRequest`. Soft-delete handled by
`BaseRepository` (every read filters `deleted_at IS NULL`).

`count_active_services` (single, for the delete-with-children guard) and
`count_active_services_map` (batch, for the paginated list) are live as of
phase 2. `count_active_products` lands in phase 3 with the Product model.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.models.service import Service
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

    async def count_active_services(self, db: AsyncSession, vertical_id: str) -> int:
        """Count non-deleted services under one vertical (delete guard)."""
        result = await db.execute(
            select(func.count(Service.id)).where(
                Service.vertical_id == vertical_id,
                Service.deleted_at.is_(None),
            )
        )
        return result.scalar_one()

    async def count_active_services_map(
        self, db: AsyncSession, vertical_ids: list[str]
    ) -> dict[str, int]:
        """Batch service counts for a page of verticals — one query, no N+1.

        Returns a `{vertical_id: count}` map; verticals with zero services are
        simply absent (the caller defaults them to 0)."""
        if not vertical_ids:
            return {}
        result = await db.execute(
            select(Service.vertical_id, func.count(Service.id))
            .where(
                Service.vertical_id.in_(vertical_ids),
                Service.deleted_at.is_(None),
            )
            .group_by(Service.vertical_id)
        )
        return {row[0]: row[1] for row in result.all()}


vertical_repository = VerticalRepository()
