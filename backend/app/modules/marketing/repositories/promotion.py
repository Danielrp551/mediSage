"""
Promotion repository. `ALLOWED_FIELDS` = solo columnas REALES (lección cd10c78: nunca
products_count/campaigns_count denormalizados). El M:N campaign_promotion se opera por el
relationship `Promotion.campaigns` (mold role/permission); el M:N promotion_product por
`promotion_product_repository` (join propio, sin relationship en Product).
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

    async def get_for_update(self, db: AsyncSession, promotion_id: str) -> Promotion | None:
        """SELECT ... FOR UPDATE para serializar el chequeo de max_uses en `apply` (caso
        válido de FOR UPDATE: lockea la fila promotion EXISTENTE, §13). Postgres-only; no-op
        en sqlite/smoke. Se usa SIEMPRE en apply por simplicidad."""
        result = await db.execute(
            select(Promotion)
            .where(Promotion.id == promotion_id, Promotion.deleted_at.is_(None))
            .with_for_update()
        )
        return result.scalars().first()

    async def promotion_name_map(self, db: AsyncSession, ids: list[str]) -> dict[str, str]:
        """Batch id→name para denormalizar promotion_name en PromotionUsage (mold
        campaign_name_map). Solo promos vivas."""
        if not ids:
            return {}
        result = await db.execute(
            select(Promotion.id, Promotion.name).where(
                Promotion.id.in_(ids), Promotion.deleted_at.is_(None)
            )
        )
        return {row[0]: row[1] for row in result.all()}


promotion_repository = PromotionRepository()
