"""
Service repository. `ALLOWED_FIELDS` whitelists the columns the frontend
can filter/sort dynamically via `QueryRequest` — `vertical_id` is included
so the Services page can filter by parent vertical. Soft-delete handled by
`BaseRepository` (every read filters `deleted_at IS NULL`).

`get_full` eager-loads the parent `vertical` with `selectinload` (one extra
batched query, never N+1) so the service layer can hydrate the denormalized
`vertical_name` onto ServiceItem/ServiceDetail. `list_active` maps rows to
`ServiceOption`, which never reads the relationship, so it deliberately does
NOT eager-load — matching `VerticalRepository.list_active`.

The `count_active_products*` pair is live as of phase 3: it powers the
denormalized `products_count` on each ServiceItem and the delete-with-children
guard in `services/service.py:soft_delete`.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.catalog.models.product import Product
from app.modules.catalog.models.service import Service
from app.shared.base_repository import BaseRepository


class ServiceRepository(BaseRepository[Service]):
    ALLOWED_FIELDS: set[str] = {
        "vertical_id",
        "code",
        "name",
        "active",
        "display_order",
        "created_on",
        "updated_on",
    }

    def __init__(self) -> None:
        super().__init__(Service)

    async def get_by_vertical_and_code(
        self, db: AsyncSession, vertical_id: str, code: str
    ) -> Service | None:
        result = await db.execute(
            select(Service).where(
                Service.vertical_id == vertical_id,
                Service.code == code,
                Service.deleted_at.is_(None),
            )
        )
        return result.scalars().first()

    async def get_full(self, db: AsyncSession, service_id: str) -> Service | None:
        return await self.get_by_id(db, service_id, load=(selectinload(Service.vertical),))

    async def list_active(self, db: AsyncSession, vertical_id: str | None = None) -> list[Service]:
        # No eager-load: the only consumer maps rows to ServiceOption, which
        # never touches `service.vertical`. Loading it here would be a wasted
        # batched SELECT per request.
        stmt = (
            select(Service)
            .where(Service.active.is_(True), Service.deleted_at.is_(None))
            .order_by(Service.display_order.asc(), Service.name.asc())
        )
        if vertical_id is not None:
            stmt = stmt.where(Service.vertical_id == vertical_id)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def count_active_products(self, db: AsyncSession, service_id: str) -> int:
        """Count non-deleted products under one service (delete guard)."""
        result = await db.execute(
            select(func.count(Product.id)).where(
                Product.service_id == service_id,
                Product.deleted_at.is_(None),
            )
        )
        return result.scalar_one()

    async def count_active_products_map(
        self, db: AsyncSession, service_ids: list[str]
    ) -> dict[str, int]:
        """Batch product counts for a page of services — one query, no N+1."""
        if not service_ids:
            return {}
        result = await db.execute(
            select(Product.service_id, func.count(Product.id))
            .where(
                Product.service_id.in_(service_ids),
                Product.deleted_at.is_(None),
            )
            .group_by(Product.service_id)
        )
        return {row[0]: row[1] for row in result.all()}


service_repository = ServiceRepository()
