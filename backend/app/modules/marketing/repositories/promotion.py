"""
Promotion repository. `ALLOWED_FIELDS` = solo columnas REALES (lección cd10c78: nunca
products_count/campaigns_count denormalizados). El M:N campaign_promotion se opera por el
relationship `Promotion.campaigns` (mold role/permission); el M:N promotion_product por
`promotion_product_repository` (join propio, sin relationship en Product).

⚠ SUBSET F2: `get_for_update` (lock de max_uses en apply) y `promotion_name_map` (denorm en
usage) llegan en F3.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.marketing.models.promotion import Promotion
from app.shared.base_repository import BaseRepository


class PromotionRepository(BaseRepository[Promotion]):
    ALLOWED_FIELDS: set[str] = {
        "code",
        "name",
        "discount_type",
        "currency",
        "start_date",
        "end_date",
        "applies_to_all_products",
        "active",
        "created_on",
        "updated_on",
    }

    def __init__(self) -> None:
        super().__init__(Promotion)

    async def get_by_code(self, db: AsyncSession, code: str) -> Promotion | None:
        result = await db.execute(
            select(Promotion).where(Promotion.code == code, Promotion.deleted_at.is_(None))
        )
        return result.scalars().first()

    async def list_active(self, db: AsyncSession) -> list[Promotion]:
        result = await db.execute(
            select(Promotion)
            .where(Promotion.active.is_(True), Promotion.deleted_at.is_(None))
            .order_by(Promotion.name.asc())
        )
        return list(result.scalars().all())

    async def get_by_ids(self, db: AsyncSession, ids: list[str]) -> list[Promotion]:
        """Batch (resuelve los objetos al setear el M:N de una campaña — mold role)."""
        if not ids:
            return []
        result = await db.execute(
            select(Promotion).where(Promotion.id.in_(ids), Promotion.deleted_at.is_(None))
        )
        return list(result.scalars().all())


promotion_repository = PromotionRepository()
