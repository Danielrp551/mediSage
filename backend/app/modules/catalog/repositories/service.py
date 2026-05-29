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

`count_active_products` is added in phase 3 when the Product model exists;
for now the service layer reports `products_count = 0`.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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


service_repository = ServiceRepository()
