"""
M:N de marketing. PK compuesta + FK CASCADE (borrar la promo/campaña/producto limpia
sus vínculos). `campaign_promotion` vincula campañas con promociones (relationship ORM en
ambos lados: Campaign.promotions ↔ Promotion.campaigns). `promotion_product` vincula
promociones con productos de catalog (SIN relationship en Product — no tocar catalog; se
resuelve por join propio en PromotionProductRepository).
"""

from __future__ import annotations

from sqlalchemy import Column, ForeignKey, String, Table

from app.core.database import Base

campaign_promotion = Table(
    "campaign_promotion",
    Base.metadata,
    Column(
        "campaign_id",
        String(36),
        ForeignKey("campaign.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "promotion_id",
        String(36),
        ForeignKey("promotion.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

promotion_product = Table(
    "promotion_product",
    Base.metadata,
    Column(
        "promotion_id",
        String(36),
        ForeignKey("promotion.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "product_id",
        String(36),
        ForeignKey("product.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)
