"""
PromotionUsage repository. `ALLOWED_FIELDS` = solo columnas REALES (lección cd10c78: nunca
denormalizados como promotion_name/person_name). SIN `updated_on` (audit inmutable, sin
SoftDelete). Provee los conteos que `apply` usa para los límites + el resumen de uso.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Row, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.marketing.models.promotion_usage import PromotionUsage
from app.shared.base_repository import BaseRepository


class PromotionUsageRepository(BaseRepository[PromotionUsage]):
    ALLOWED_FIELDS: set[str] = {
        "promotion_id",
        "person_id",
        "product_id",
        "appointment_id",
        "campaign_id",
        "currency",
        "created_on",
    }

    def __init__(self) -> None:
        super().__init__(PromotionUsage)

    async def get_by_appointment(
        self, db: AsyncSession, appointment_id: str
    ) -> PromotionUsage | None:
        """Pre-check no-stacking (apply paso 6). El UNIQUE parcial es el backstop de carrera."""
        result = await db.execute(
            select(PromotionUsage).where(PromotionUsage.appointment_id == appointment_id)
        )
        return result.scalars().first()

    async def count_for_promotion(self, db: AsyncSession, promotion_id: str) -> int:
        """max_uses_total (apply paso 7) + total_uses del detalle de promoción."""
        result = await db.execute(
            select(func.count())
            .select_from(PromotionUsage)
            .where(PromotionUsage.promotion_id == promotion_id)
        )
        return result.scalar_one()

    async def count_for_promotion_person(
        self, db: AsyncSession, promotion_id: str, person_id: str
    ) -> int:
        """max_uses_per_person (apply paso 8)."""
        result = await db.execute(
            select(func.count())
            .select_from(PromotionUsage)
            .where(
                PromotionUsage.promotion_id == promotion_id,
                PromotionUsage.person_id == person_id,
            )
        )
        return result.scalar_one()

    async def usage_summary(
        self, db: AsyncSession, promotion_id: str
    ) -> Row[tuple[int, Decimal, Decimal, Decimal]]:
        """Row(count, sum_original, sum_discount, sum_final) — GET /usage-summary.
        `coalesce(sum, 0)` evita NULL cuando no hay usos (devuelve 0)."""
        result = await db.execute(
            select(
                func.count(),
                func.coalesce(func.sum(PromotionUsage.original_amount), 0),
                func.coalesce(func.sum(PromotionUsage.discount_amount), 0),
                func.coalesce(func.sum(PromotionUsage.final_amount), 0),
            ).where(PromotionUsage.promotion_id == promotion_id)
        )
        return result.one()


promotion_usage_repository = PromotionUsageRepository()
