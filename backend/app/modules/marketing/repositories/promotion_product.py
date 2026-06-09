"""
M:N `promotion_product` (promociones ↔ productos cubiertos). Se resuelve por query propia
(NO relationship en catalog.Product — no tocar catalog). bulk-replace (`set_products`),
conteo batch (`count_products_map`), join de lectura (`list_products_for_promotion`) y
`covers_product` (validación de cobertura en `apply`).
"""

from __future__ import annotations

from sqlalchemy import delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.models.product import Product  # solo para el join de lectura
from app.modules.marketing.models.associations import promotion_product


class PromotionProductRepository:
    async def set_products(
        self, db: AsyncSession, promotion_id: str, product_ids: list[str]
    ) -> None:
        """Bulk-replace: delete los vínculos de la promo + insert el nuevo set. El caller
        valida que cada product exista vivo en catalog."""
        await db.execute(
            delete(promotion_product).where(promotion_product.c.promotion_id == promotion_id)
        )
        if product_ids:
            await db.execute(
                insert(promotion_product),
                [{"promotion_id": promotion_id, "product_id": pid} for pid in product_ids],
            )

    async def count_products_map(
        self, db: AsyncSession, promotion_ids: list[str]
    ) -> dict[str, int]:
        """Batch promotion_id→#productos para PromotionItem.products_count (sin N+1)."""
        if not promotion_ids:
            return {}
        result = await db.execute(
            select(promotion_product.c.promotion_id, func.count())
            .where(promotion_product.c.promotion_id.in_(promotion_ids))
            .group_by(promotion_product.c.promotion_id)
        )
        return {row[0]: row[1] for row in result.all()}

    async def live_product_ids(self, db: AsyncSession, ids: list[str]) -> set[str]:
        """De `ids`, cuáles son productos VIVOS en catalog (validación pre-set: un id
        inexistente → PRODUCT_NOT_FOUND limpio en vez de IntegrityError 500 de la FK)."""
        if not ids:
            return set()
        result = await db.execute(
            select(Product.id).where(Product.id.in_(ids), Product.deleted_at.is_(None))
        )
        return {row[0] for row in result.all()}

    async def list_products_for_promotion(
        self, db: AsyncSession, promotion_id: str
    ) -> list[Product]:
        """JOIN PROPIO a catalog.Product (NO relationship en Product). Solo productos vivos.
        Powers PromotionDetail.products + GET /promotions/{id}/products."""
        result = await db.execute(
            select(Product)
            .join(promotion_product, promotion_product.c.product_id == Product.id)
            .where(
                promotion_product.c.promotion_id == promotion_id,
                Product.deleted_at.is_(None),
            )
            .order_by(Product.name.asc())
        )
        return list(result.scalars().all())

    async def covers_product(self, db: AsyncSession, promotion_id: str, product_id: str) -> bool:
        """¿El producto está en el M:N de la promo? (apply paso 5, cuando NO
        applies_to_all_products). Chequea solo la fila puente (no valida que el product
        esté vivo — eso lo hace el caller / la elegibilidad lo da por sentado)."""
        result = await db.execute(
            select(promotion_product.c.product_id).where(
                promotion_product.c.promotion_id == promotion_id,
                promotion_product.c.product_id == product_id,
            )
        )
        return result.first() is not None


promotion_product_repository = PromotionProductRepository()
