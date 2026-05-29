"""
Product repository. `ALLOWED_FIELDS` whitelists the columns the frontend can
filter/sort dynamically via `QueryRequest`. Both `service_id` and the
denormalized `vertical_id` are included so the Products page can filter by
either level of the hierarchy without a join. Soft-delete handled by
`BaseRepository` (every read filters `deleted_at IS NULL`).

`get_full` eager-loads the parent service AND its vertical (two-level
`selectinload`, one batched query each, never N+1) so the service layer can
hydrate the denormalized `service_name` + `vertical_name`. `list_active`
maps rows to `ProductOption` (columns only), so it does NOT eager-load.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.catalog.models.product import Product
from app.modules.catalog.models.service import Service
from app.shared.base_repository import BaseRepository


class ProductRepository(BaseRepository[Product]):
    ALLOWED_FIELDS: set[str] = {
        "service_id",
        "vertical_id",
        "code",
        "name",
        "active",
        "base_price",
        "currency",
        "duration_min",
        "requires_appointment",
        "is_package",
        "created_on",
        "updated_on",
    }

    def __init__(self) -> None:
        super().__init__(Product)

    async def get_by_service_and_code(
        self, db: AsyncSession, service_id: str, code: str
    ) -> Product | None:
        result = await db.execute(
            select(Product).where(
                Product.service_id == service_id,
                Product.code == code,
                Product.deleted_at.is_(None),
            )
        )
        return result.scalars().first()

    async def get_full(self, db: AsyncSession, product_id: str) -> Product | None:
        return await self.get_by_id(
            db,
            product_id,
            load=(selectinload(Product.service).selectinload(Service.vertical),),
        )

    async def list_active(self, db: AsyncSession, service_id: str | None = None) -> list[Product]:
        # No eager-load: the only consumer maps rows to ProductOption, which
        # reads columns only (never the service/vertical relationships).
        stmt = (
            select(Product)
            .where(Product.active.is_(True), Product.deleted_at.is_(None))
            .order_by(Product.name.asc())
        )
        if service_id is not None:
            stmt = stmt.where(Product.service_id == service_id)
        result = await db.execute(stmt)
        return list(result.scalars().all())


product_repository = ProductRepository()
