"""
Vertical repository. `ALLOWED_FIELDS` whitelists which columns the frontend
can filter/sort dynamically via `QueryRequest`. Soft-delete handled by
`BaseRepository` (every read filters `deleted_at IS NULL`).

`count_active_services` (single, for the delete-with-children guard) and
`count_active_services_map` (batch, for the paginated list) are live as of
phase 2. The `count_active_products*` pair lands in phase 3: it counts via the
denormalized `Product.vertical_id` (no join) — a non-deleted product always
belongs to a non-deleted service since a service can't be deleted while it has
active products.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.models.product import Product
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

    async def get_by_ids(self, db: AsyncSession, ids: list[str]) -> list[Vertical]:
        """Fetch live (non-deleted) verticals by id. Additive helper used by
        `clinic` to resolve the office_vertical M:N — a soft-deleted vertical is
        filtered out, so it counts as 'unknown' when attaching it to an office
        (mirrors role_repository.get_by_ids / permission_repository.get_by_ids)."""
        if not ids:
            return []
        result = await db.execute(
            select(Vertical).where(Vertical.id.in_(ids), Vertical.deleted_at.is_(None))
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

    async def count_active_products(self, db: AsyncSession, vertical_id: str) -> int:
        """Count non-deleted products in one vertical (via denormalized FK)."""
        result = await db.execute(
            select(func.count(Product.id)).where(
                Product.vertical_id == vertical_id,
                Product.deleted_at.is_(None),
            )
        )
        return result.scalar_one()

    async def count_active_products_map(
        self, db: AsyncSession, vertical_ids: list[str]
    ) -> dict[str, int]:
        """Batch product counts for a page of verticals — one query, no N+1."""
        if not vertical_ids:
            return {}
        result = await db.execute(
            select(Product.vertical_id, func.count(Product.id))
            .where(
                Product.vertical_id.in_(vertical_ids),
                Product.deleted_at.is_(None),
            )
            .group_by(Product.vertical_id)
        )
        return {row[0]: row[1] for row in result.all()}


vertical_repository = VerticalRepository()
