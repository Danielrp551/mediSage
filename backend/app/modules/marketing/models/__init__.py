"""Modelos SQLAlchemy de `marketing`.

Importarlos acá los registra en `Base.metadata` antes de que Alembic lea el esquema y
antes de resolver los relationship() por string. Orden: associations + campaign +
promotion (el M:N Campaign.promotions ↔ Promotion.campaigns necesita ambas tablas);
promotion_usage al final (sus FKs reales referencian promotion/campaign/product/person/
appointment, todas ya registradas).

Por fase: F1 `campaign.py` (Campaign) · F2 `promotion.py` (Promotion) +
`associations.py` (campaign_promotion, promotion_product) · F3 `promotion_usage.py`
(PromotionUsage, PK·A·T sin SoftDelete). Mixins del template. PKs/FKs String(36).
"""

from app.modules.marketing.models.associations import (  # noqa: F401
    campaign_promotion,
    promotion_product,
)
from app.modules.marketing.models.campaign import Campaign
from app.modules.marketing.models.promotion import Promotion
from app.modules.marketing.models.promotion_usage import PromotionUsage

__all__ = [
    "Campaign",
    "Promotion",
    "PromotionUsage",
    "campaign_promotion",
    "promotion_product",
]
